"""
PASO 6-8: entrenar y evaluar el clasificador (KNN) con los landmarks de landmarks.csv.

- Divide en entrenamiento / prueba POR VOLUNTARIO (nadie aparece en los dos grupos).
- Excluye letras con muy pocos voluntarios (no se pueden aprender ni evaluar bien).
- Imprime la precisión global, por letra y las confusiones más frecuentes.
- Exporta `modelo_knn.json`: muestras de referencia para clasificar en el navegador
  (KNN con distancia euclidiana y voto simple entre los k vecinos; la confianza es la
  fracción de vecinos que votan por la letra ganadora).

- Con --rotacion G añade a la base copias de cada muestra giradas ±G grados en el plano
  de la imagen (ver 05_ajustar_knn.py: tolera manos inclinadas frente a la webcam).
  Solo cambia qué muestras van al JSON; el formato y lsc-reconocedor.js no cambian.

Uso:
  python 03_entrenar.py --csv landmarks.csv --rotacion 15
  python 03_entrenar.py --csv landmarks.csv --k 5 --prueba 0.2 --max-por-letra 150
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupShuffleSplit
from sklearn.neighbors import KNeighborsClassifier

COLUMNAS = [f"{eje}{i}" for i in range(21) for eje in ("x", "y", "z")]


def submuestrear(df, maximo, seed):
    """Hasta `maximo` muestras por letra, repartidas por turnos entre voluntarios
    (así la base de referencia conserva variedad de personas)."""
    rng = np.random.default_rng(seed)
    elegidos_total = []
    for _, g in df.groupby("letra"):
        colas = []
        for _, gv in g.groupby("voluntario"):
            ii = gv.index.to_numpy().copy()
            rng.shuffle(ii)
            colas.append(list(ii))
        rng.shuffle(colas)
        elegidos = []
        while len(elegidos) < maximo and any(colas):
            for c in colas:
                if c and len(elegidos) < maximo:
                    elegidos.append(c.pop())
        elegidos_total.extend(elegidos)
    return df.loc[elegidos_total]


def aumentar_rotacion(df, grados):
    """Añade copias giradas ±`grados` alrededor de la muñeca en el plano x-y. Conserva la
    normalización (muñeca en el origen, distancia al punto 9 igual a 1)."""
    if not grados:
        return df
    P = df[COLUMNAS].to_numpy(dtype=np.float64).reshape(-1, 21, 3)
    copias = [df]
    for g in (grados, -grados):
        t = np.deg2rad(g)
        R = P.copy()
        R[:, :, 0] = P[:, :, 0] * np.cos(t) - P[:, :, 1] * np.sin(t)
        R[:, :, 1] = P[:, :, 0] * np.sin(t) + P[:, :, 1] * np.cos(t)
        copia = df.copy()
        copia[COLUMNAS] = R.reshape(len(df), -1)
        copias.append(copia)
    return pd.concat(copias, ignore_index=True)


def knn(k):
    return KNeighborsClassifier(n_neighbors=k, weights="uniform", metric="euclidean")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="landmarks.csv")
    ap.add_argument("--k", type=int, default=5, help="vecinos del KNN que se exporta")
    ap.add_argument("--prueba", type=float, default=0.2, help="fracción de voluntarios para prueba")
    ap.add_argument("--min-voluntarios", type=int, default=5,
                    help="letras con menos voluntarios que esto se excluyen")
    ap.add_argument("--max-por-letra", type=int, default=150,
                    help="muestras de referencia por letra en el JSON exportado")
    ap.add_argument("--rotacion", type=float, default=0,
                    help="grados de las copias giradas que se añaden a la base (0 = sin aumento)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--salida", default="modelo_knn.json")
    args = ap.parse_args()

    # keep_default_na=False: para que una letra como "NA" no se lea como dato vacío
    df = pd.read_csv(args.csv, dtype={"voluntario": str, "letra": str}, keep_default_na=False)
    df = df.reset_index(drop=True)
    print(f"{len(df)} muestras, {df.voluntario.nunique()} voluntarios, {df.letra.nunique()} letras\n")

    # --- letras con pocos voluntarios
    resumen = df.groupby("letra").agg(muestras=("letra", "size"), voluntarios=("voluntario", "nunique"))
    print(resumen.to_string())
    pocas = resumen[resumen.voluntarios < args.min_voluntarios].index.tolist()
    if pocas:
        print(f"\nExcluidas por tener menos de {args.min_voluntarios} voluntarios: {', '.join(pocas)}")
        df = df[~df.letra.isin(pocas)].reset_index(drop=True)
    if "desconocido" in set(df.voluntario):
        print("\nAVISO: hay imágenes sin voluntario ('desconocido'); se tratan como UNA sola persona, "
              "así que la división por persona no es fiable para esas.")

    letras = sorted(df.letra.unique())
    if df.voluntario.nunique() < 4 or len(letras) < 2:
        raise SystemExit("Muy pocos voluntarios o letras para evaluar.")

    X = df[COLUMNAS].to_numpy(dtype=np.float64)
    y = df.letra.to_numpy()

    # --- división por voluntario
    gss = GroupShuffleSplit(n_splits=1, test_size=args.prueba, random_state=args.seed)
    tr, te = next(gss.split(X, y, groups=df.voluntario))
    vol_tr, vol_te = df.voluntario.iloc[tr].nunique(), df.voluntario.iloc[te].nunique()
    print(f"\nEntrenamiento: {len(tr)} muestras de {vol_tr} voluntarios | "
          f"Prueba: {len(te)} muestras de {vol_te} voluntarios (personas que el modelo NO vio)")

    # --- efecto de k (informativo)
    print("\nPrecisión en voluntarios de prueba según k:")
    for k in sorted({1, 3, 5, 9, args.k}):
        acc = knn(k).fit(X[tr], y[tr]).score(X[te], y[te])
        marca = "  <- el que se exporta" if k == args.k else ""
        print(f"  k={k:<3} {100 * acc:5.1f}%{marca}")

    # --- evaluación con la MISMA base reducida que se exportará (estimación honesta)
    ref_tr = submuestrear(aumentar_rotacion(df.iloc[tr], args.rotacion), args.max_por_letra, args.seed)
    modelo = knn(args.k).fit(ref_tr[COLUMNAS].to_numpy(), ref_tr.letra.to_numpy())
    pred = modelo.predict(X[te])
    acc = float((pred == y[te]).mean())
    aumento = f", rotación ±{args.rotacion:g}°" if args.rotacion else ""
    print(f"\nPrecisión global con la base reducida ({args.max_por_letra} muestras/letra, k={args.k}"
          f"{aumento}): {100 * acc:.1f}%")

    # --- por letra y confusiones
    print("\nPrecisión por letra (en voluntarios de prueba):")
    filas = []
    for letra in letras:
        m = y[te] == letra
        if m.sum() == 0:
            continue
        filas.append((letra, int(m.sum()), 100 * float((pred[m] == letra).mean())))
    for letra, n, p in sorted(filas, key=lambda f: f[2]):
        alerta = "  <-- revisar" if p < 80 else ""
        print(f"  {letra:<4} n={n:<5} {p:5.1f}%{alerta}")

    conf = {}
    for real, p in zip(y[te], pred):
        if real != p:
            conf[(real, p)] = conf.get((real, p), 0) + 1
    if conf:
        print("\nConfusiones más frecuentes (real -> predicha):")
        for (a, b), c in sorted(conf.items(), key=lambda kv: -kv[1])[:10]:
            print(f"  {a} -> {b}: {c}")

    # --- exportar: base de referencia con TODOS los voluntarios
    ref = submuestrear(aumentar_rotacion(df, args.rotacion), args.max_por_letra, args.seed)
    indice = {l: i for i, l in enumerate(letras)}
    datos = {
        "version": 1,
        "k": args.k,
        "letras": letras,
        "n_caracteristicas": 63,
        "metrica": "euclidiana",
        "votacion": "simple; confianza = votos de la letra ganadora / k",
        "aumento_rotacion_grados": args.rotacion,
        "normalizacion": ("puntos en pixeles (x*ancho, y*alto, z*ancho); restar muneca (punto 0); "
                          "dividir entre distancia 3D muneca-punto 9; si la mano es 'Left' invertir signo de x"),
        "X": [[round(float(v), 3) for v in fila] for fila in ref[COLUMNAS].to_numpy()],
        "y": [indice[l] for l in ref.letra],
    }
    Path(args.salida).write_text(json.dumps(datos, separators=(",", ":")), encoding="utf-8")
    kb = Path(args.salida).stat().st_size / 1024
    print(f"\nExportado -> {args.salida} ({len(ref)} muestras de referencia, {kb:.0f} KB, "
          f"{len(letras)} letras: {', '.join(letras)})")


if __name__ == "__main__":
    main()
