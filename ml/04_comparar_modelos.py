"""
PASO 9: comparar formas de representar la mano y modelos, con validación cruzada
POR VOLUNTARIO (5 particiones: cada persona queda alguna vez como "prueba"). Es una
medida bastante más estable que el único corte de 7 voluntarios de 03_entrenar.py.

Representaciones (todas parten de los landmarks ya normalizados de landmarks.csv):
  base63  los 63 números tal cual (lo que usa 03_entrenar.py)
  xy      solo x e y (la profundidad z que estima MediaPipe es ruidosa)
  xy_rot  x e y girados para que la mano quede siempre "hacia arriba"
  dist    las 210 distancias entre todos los pares de puntos (no dependen de la
          rotación ni de si la mano es izquierda o derecha)

Modelos: KNN (el actual), SVM, red neuronal pequeña (MLP) y regresión logística.

Uso:
  python 04_comparar_modelos.py --csv landmarks.csv
  python 04_comparar_modelos.py --csv landmarks.csv --ultimos 3
"""
import argparse
import re
import time
import warnings

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score
from sklearn.model_selection import GroupKFold
from sklearn.neighbors import KNeighborsClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

warnings.filterwarnings("ignore")
COLUMNAS = [f"{eje}{i}" for i in range(21) for eje in ("x", "y", "z")]
IU = np.triu_indices(21, 1)


# ---------------------------------------------------------------- representaciones
def puntos(X):
    return X.reshape(-1, 21, 3)


def f_base63(X):
    return X


def f_xy(X):
    return puntos(X)[:, :, :2].reshape(len(X), -1)


def girar_xy(X):
    """Gira en el plano de la imagen para que el vector muñeca -> punto 9 apunte hacia arriba."""
    P = puntos(X)[:, :, :2]
    v = P[:, 9, :]
    delta = -np.pi / 2 - np.arctan2(v[:, 1], v[:, 0])
    c, s = np.cos(delta)[:, None], np.sin(delta)[:, None]
    x, y = P[:, :, 0], P[:, :, 1]
    return np.stack([x * c - y * s, x * s + y * c], axis=2)


def f_xy_rot(X):
    return girar_xy(X).reshape(len(X), -1)


def f_dist(X):
    P = puntos(X)
    d = np.linalg.norm(P[:, :, None, :] - P[:, None, :, :], axis=3)
    return d[:, IU[0], IU[1]]


REPRESENTACIONES = {"base63": f_base63, "xy": f_xy, "xy_rot": f_xy_rot, "dist": f_dist}


def modelos(seed):
    return {
        "KNN k=5": lambda: KNeighborsClassifier(n_neighbors=5),
        "SVM": lambda: make_pipeline(StandardScaler(), SVC(C=10, kernel="rbf", gamma="scale")),
        "MLP": lambda: make_pipeline(StandardScaler(), MLPClassifier(
            hidden_layer_sizes=(128, 64), alpha=1e-3, max_iter=400,
            early_stopping=True, random_state=seed)),
        "LogReg": lambda: make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000)),
    }


# ---------------------------------------------------------------- utilidades
def clave_natural(texto):
    return [(0, int(t), "") if t.isdigit() else (1, 0, t.lower()) for t in re.split(r"(\d+)", texto)]


def quedarse_con_ultimos(df, k):
    """Por cada (voluntario, letra), conserva solo los k últimos archivos en orden natural
    (los fotogramas finales de la secuencia, cuando la mano ya llegó a la seña)."""
    orden = sorted(range(len(df)), key=lambda i: clave_natural(df.archivo.iat[i]))
    df = df.iloc[orden]
    primero = df.groupby(["voluntario", "letra"], sort=False).head(1).iloc[0]
    grupo = df[(df.voluntario == primero.voluntario) & (df.letra == primero.letra)].archivo.tolist()
    print(f"--ultimos {k}: ejemplo del orden de archivos de {primero.voluntario} / {primero.letra} "
          f"(se conservan los {k} últimos):")
    for i, a in enumerate(grupo):
        print(f"   {'*' if i >= len(grupo) - k else ' '} {a}")
    print("   Si ese orden NO es el de la secuencia real, no uses --ultimos.\n")
    return df.groupby(["voluntario", "letra"], sort=False).tail(k).reset_index(drop=True)


def evaluar(X, y, grupos, fabrica, n_splits):
    oof = y.copy()
    accs = []
    for tr, te in GroupKFold(n_splits=n_splits).split(X, y, grupos):
        oof[te] = fabrica().fit(X[tr], y[tr]).predict(X[te])
        accs.append(float((oof[te] == y[te]).mean()))
    return oof, accs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="landmarks.csv")
    ap.add_argument("--min-voluntarios", type=int, default=5)
    ap.add_argument("--particiones", type=int, default=5)
    ap.add_argument("--ultimos", type=int, default=0,
                    help="usar solo los N últimos fotogramas de cada seña de cada voluntario")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--salida", default="comparacion_modelos.csv")
    args = ap.parse_args()

    df = pd.read_csv(args.csv, dtype={"voluntario": str, "letra": str, "archivo": str},
                     keep_default_na=False).reset_index(drop=True)
    nv = df.groupby("letra").voluntario.nunique()
    df = df[df.letra.isin(nv[nv >= args.min_voluntarios].index)].reset_index(drop=True)
    if args.ultimos:
        df = quedarse_con_ultimos(df, args.ultimos)
    print(f"{len(df)} muestras, {df.voluntario.nunique()} voluntarios, {df.letra.nunique()} letras\n")

    # diagnóstico de la etiqueta Left/Right (cada voluntario usa una sola mano dominante)
    izq = df.assign(izq=(df.mano == "Left")).groupby("voluntario").izq.mean()
    mixtos = int(((izq > 0.1) & (izq < 0.9)).sum())
    print(f"Etiqueta de mano: {100 * (df.mano == 'Left').mean():.0f} % de las muestras salieron como 'Left'; "
          f"{mixtos} de {len(izq)} voluntarios tienen etiquetas mezcladas.")
    if mixtos > len(izq) * 0.2:
        print("  -> Muchos voluntarios con etiqueta mezclada: la etiqueta Left/Right no es fiable aquí; "
              "la representación 'dist' no depende de ella.")
    print()

    X = df[COLUMNAS].to_numpy(dtype=np.float64)
    y = df.letra.to_numpy()
    grupos = df.voluntario.to_numpy()
    n_splits = min(args.particiones, df.voluntario.nunique())

    filas, oofs = [], {}
    print(f"Validación cruzada por voluntario ({n_splits} particiones):")
    for rn, rf in REPRESENTACIONES.items():
        Xr = rf(X)
        for mn, fab in modelos(args.seed).items():
            t0 = time.time()
            oof, accs = evaluar(Xr, y, grupos, fab, n_splits)
            oofs[(rn, mn)] = oof
            filas.append({"representacion": rn, "modelo": mn, "precision": 100 * np.mean(accs),
                          "desv": 100 * np.std(accs),
                          "balanceada": 100 * balanced_accuracy_score(y, oof)})
            print(f"  {rn:<8}{mn:<9}{filas[-1]['precision']:5.1f} %  (± {filas[-1]['desv']:.1f})   "
                  f"[{time.time() - t0:.0f} s]", flush=True)

    res = pd.DataFrame(filas).sort_values("precision", ascending=False).reset_index(drop=True)
    res.to_csv(args.salida, index=False)
    print("\nRanking (precisión media en voluntarios no vistos):")
    print(res.round(1).to_string(index=False))
    base = res[(res.representacion == "base63") & (res.modelo == "KNN k=5")].precision.iloc[0]
    mejor = res.iloc[0]
    print(f"\nLo que ya tenías (base63 + KNN): {base:.1f} %  |  mejor: {mejor.representacion} + "
          f"{mejor.modelo}: {mejor.precision:.1f} %")

    # detalle del mejor
    oof = oofs[(mejor.representacion, mejor.modelo)]
    print(f"\nPrecisión por letra con la mejor combinación:")
    por_letra = sorted(((l, 100 * float((oof[y == l] == l).mean())) for l in np.unique(y)), key=lambda t: t[1])
    for l, p in por_letra:
        print(f"  {l:<4}{p:5.1f} %{'  <-- revisar' if p < 80 else ''}")

    conf = {}
    for i in np.where(oof != y)[0]:
        conf.setdefault((y[i], oof[i]), []).append(i)
    top = sorted(conf.items(), key=lambda kv: -len(kv[1]))[:5]
    print("\nConfusiones más frecuentes (real -> predicha) y algunos archivos mal clasificados,")
    print("para que abras las imágenes y veas si la seña está mal etiquetada o es de verdad parecida:")
    for (a, b), idx in top:
        print(f"  {a} -> {b}: {len(idx)}")
        for i in idx[:3]:
            print(f"      {df.voluntario.iat[i]} / {df.archivo.iat[i]}")
    print(f"\nTabla guardada en {args.salida}")


if __name__ == "__main__":
    main()
