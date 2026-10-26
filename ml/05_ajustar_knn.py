"""
PASO 10: ajustar la base de referencia del KNN SIN cambiar el formato del modelo
(el navegador sigue usando lsc-reconocedor.js tal cual: 63 valores, euclidiana,
voto simple entre k=5 vecinos).

Solo cambia QUÉ muestras van en `modelo_knn.json`:
  max      muestras de referencia por letra (más = JSON más grande)
  frames   usar todos los fotogramas o solo los finales (los primeros de cada seña
           son la transición: la mano todavía no llegó a la forma)
  enn      quitar muestras cuyo vecindario vota por otra letra (ruido / mal etiquetadas)
  rot      añadir copias giradas en el plano de la imagen (± cada ángulo de la
           tupla), para tolerar una mano inclinada frente a la webcam

Se mide con validación cruzada POR VOLUNTARIO y con la regla del frontend: un
fotograma "cuenta" si la letra predicha es la correcta con confianza >= 0.6.

  precision   letra predicha == real (sin umbral)
  ok@0.6      correcta y con confianza >= 0.6        (lo que el usuario ve como acierto)
  falso@0.6   incorrecta pero con confianza >= 0.6   (aceptaría otra letra)
  ok@0.6_fin  ok@0.6 solo en los fotogramas finales  (mano ya quieta, lo más parecido a la webcam)
  ok@0.6_rot  ok@0.6 con la prueba girada ±15°       (robustez a una mano inclinada)

Uso:
  python 05_ajustar_knn.py --csv landmarks.csv
"""
import argparse
import itertools
import re
import time

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold
from sklearn.neighbors import KNeighborsClassifier

COLUMNAS = [f"{eje}{i}" for i in range(21) for eje in ("x", "y", "z")]
K = 5
UMBRAL = 0.6          # el mismo que UMBRAL_CONFIANZA en evaluacion.html
PRIMER_FRAME_FINAL = 2  # fotogramas 2..5 de cada seña se consideran "finales"


# ---------------------------------------------------------------- transformaciones
def rotar_xy(X, grados):
    """Gira los puntos en el plano de la imagen alrededor de la muñeca (origen).
    Conserva la normalización: la muñeca sigue en 0 y la distancia al punto 9 no cambia."""
    t = np.deg2rad(grados)
    c, s = np.cos(t), np.sin(t)
    P = X.reshape(-1, 21, 3).copy()
    x, y = P[:, :, 0].copy(), P[:, :, 1].copy()
    P[:, :, 0] = x * c - y * s
    P[:, :, 1] = x * s + y * c
    return P.reshape(len(X), -1)


def numero_frame(archivo):
    m = re.search(r"_(\d+)\.[A-Za-z]+$", archivo)
    return int(m.group(1)) if m else -1


# ---------------------------------------------------------------- base de referencia
def submuestrear(idx, letras, voluntarios, maximo, rng):
    """Hasta `maximo` índices por letra, repartidos por turnos entre voluntarios
    (misma idea que 03_entrenar.py)."""
    elegidos = []
    for letra in np.unique(letras[idx]):
        il = idx[letras[idx] == letra]
        colas = []
        for v in np.unique(voluntarios[il]):
            c = il[voluntarios[il] == v].copy()
            rng.shuffle(c)
            colas.append(list(c))
        rng.shuffle(colas)
        tomados = []
        while len(tomados) < maximo and any(colas):
            for c in colas:
                if c and len(tomados) < maximo:
                    tomados.append(c.pop())
        elegidos.extend(tomados)
    return np.array(elegidos, dtype=int)


def limpiar_enn(X, y, k=K):
    """Edited Nearest Neighbours: descarta la muestra si la mayoría de sus k vecinos
    (sin contarse a sí misma) es de otra letra."""
    knn = KNeighborsClassifier(n_neighbors=k + 1).fit(X, y)
    vecinos = knn.kneighbors(X, return_distance=False)[:, 1:]
    iguales = (y[vecinos] == y[:, None]).sum(axis=1)
    return iguales * 2 > k


def construir_base(X, y, frames, voluntarios, idx, cfg, rng):
    """Devuelve (Xref, yref) a partir de las muestras `idx` (solo entrenamiento)."""
    if cfg["frames"] == "finales":
        idx = idx[frames[idx] >= PRIMER_FRAME_FINAL]
    if cfg["enn"]:
        idx = idx[limpiar_enn(X[idx], y[idx])]

    Xb, yb, vb = X[idx], y[idx], voluntarios[idx]
    if cfg["rot"]:
        angulos = [s * g for g in cfg["rot"] for s in (1, -1)]
        Xb = np.vstack([Xb] + [rotar_xy(Xb, a) for a in angulos])
        copias = len(angulos) + 1
        yb, vb = np.tile(yb, copias), np.tile(vb, copias)

    if cfg["max"]:
        sel = submuestrear(np.arange(len(yb)), yb, vb, cfg["max"], rng)
        Xb, yb = Xb[sel], yb[sel]
    return Xb, yb


def predecir(Xref, yref, Xte):
    """Igual que ClasificadorKNN.predecir: voto simple; en empate gana la letra
    de menor índice (sklearn también toma la primera clase en orden)."""
    knn = KNeighborsClassifier(n_neighbors=K, weights="uniform").fit(Xref, yref)
    proba = knn.predict_proba(Xte)
    return knn.classes_[proba.argmax(axis=1)], proba.max(axis=1)


# ---------------------------------------------------------------- evaluación
def evaluar(X, y, frames, voluntarios, cfg, n_splits, seed):
    rng = np.random.default_rng(seed)
    m = {k: [] for k in ("precision", "ok@0.6", "falso@0.6", "ok@0.6_fin", "ok@0.6_rot")}
    tamanos = []
    for tr, te in GroupKFold(n_splits=n_splits).split(X, y, voluntarios):
        Xref, yref = construir_base(X, y, frames, voluntarios, tr, cfg, rng)
        tamanos.append(len(yref))

        pred, conf = predecir(Xref, yref, X[te])
        bien, seguro = pred == y[te], conf >= UMBRAL
        m["precision"].append(bien.mean())
        m["ok@0.6"].append((bien & seguro).mean())
        m["falso@0.6"].append((~bien & seguro).mean())
        fin = frames[te] >= PRIMER_FRAME_FINAL
        m["ok@0.6_fin"].append((bien & seguro)[fin].mean())

        aciertos_rot = []
        for g in (15, -15):
            p, c = predecir(Xref, yref, rotar_xy(X[te], g))
            aciertos_rot.append(((p == y[te]) & (c >= UMBRAL)).mean())
        m["ok@0.6_rot"].append(np.mean(aciertos_rot))

    fila = {k: 100 * float(np.mean(v)) for k, v in m.items()}
    fila["desv"] = 100 * float(np.std(m["ok@0.6"]))
    fila["muestras_ref"] = int(np.mean(tamanos))
    return fila


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="landmarks.csv")
    ap.add_argument("--min-voluntarios", type=int, default=5)
    ap.add_argument("--particiones", type=int, default=5)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--salida", default="ajuste_knn.csv")
    args = ap.parse_args()

    df = pd.read_csv(args.csv, dtype={"voluntario": str, "letra": str, "archivo": str},
                     keep_default_na=False).reset_index(drop=True)
    nv = df.groupby("letra").voluntario.nunique()
    df = df[df.letra.isin(nv[nv >= args.min_voluntarios].index)].reset_index(drop=True)

    X = df[COLUMNAS].to_numpy(dtype=np.float64)
    y = df.letra.to_numpy()
    voluntarios = df.voluntario.to_numpy()
    frames = df.archivo.map(numero_frame).to_numpy()
    if (frames < 0).any():
        raise SystemExit("Hay archivos sin número de fotograma (se esperaba ..._<n>.jpg).")
    print(f"{len(df)} muestras, {df.voluntario.nunique()} voluntarios, {df.letra.nunique()} letras; "
          f"fotogramas {frames.min()}..{frames.max()}\n")

    rejilla = [dict(zip(("max", "frames", "enn", "rot"), v)) for v in itertools.product(
        (150, 300),
        ("todos", "finales"),
        (False, True),
        ((), (15,), (10, 20)),
    )]

    filas = []
    for cfg in rejilla:
        t0 = time.time()
        fila = {**cfg, **evaluar(X, y, frames, voluntarios, cfg, args.particiones, args.seed)}
        filas.append(fila)
        print(f"  max={cfg['max'] or 'todas':<6} frames={cfg['frames']:<8} enn={str(cfg['enn']):<6} "
              f"rot={str(cfg['rot']):<11} | ok@0.6 {fila['ok@0.6']:5.1f}  fin {fila['ok@0.6_fin']:5.1f}  "
              f"rot {fila['ok@0.6_rot']:5.1f}  falso {fila['falso@0.6']:4.1f}  "
              f"ref {fila['muestras_ref']:>5}  [{time.time() - t0:.0f} s]", flush=True)

    res = pd.DataFrame(filas).sort_values("ok@0.6_fin", ascending=False).reset_index(drop=True)
    res.to_csv(args.salida, index=False)
    print("\nRanking por ok@0.6_fin (fotogramas finales, regla del frontend):")
    print(res.round(1).to_string(index=False))


if __name__ == "__main__":
    main()
