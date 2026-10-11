"""
PASO 3: probar MediaPipe en unas pocas imágenes por letra ANTES de procesar todo.

Compara tres formas de pasarle la imagen al detector (original / agrandada /
agrandada + margen) y muestra el % de imágenes donde detecta mano, por letra.
También guarda unas cuantas imágenes con los puntos dibujados para revisarlas a ojo.

Uso:
  python 01_probar_deteccion.py --dataset data/LSC70ANH --layout voluntario/letra
  python 01_probar_deteccion.py --dataset data/LSC70ANH --muestras 30 --letras A B C
"""
import argparse
import csv
import random
from collections import defaultdict
from pathlib import Path

import cv2

from landmarks_utils import (crear_detector, detectar_mano, dibujar,
                             leer_imagen, listar_imagenes, preprocesar)

MODOS = ["original", "resize", "resize+pad"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True, help="carpeta raíz con las imágenes")
    ap.add_argument("--layout", default="voluntario/letra",
                    choices=["voluntario/letra", "letra/voluntario"])
    ap.add_argument("--letras", nargs="*", help="solo estas letras (por defecto todas)")
    ap.add_argument("--muestras", type=int, default=20, help="imágenes por letra a probar")
    ap.add_argument("--lado", type=int, default=480)
    ap.add_argument("--confianza", type=float, default=0.3)
    ap.add_argument("--salida", default="salida_prueba")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    items = listar_imagenes(args.dataset, args.layout, args.letras)
    if not items:
        raise SystemExit("No encontré imágenes. Revisa --dataset y --layout.")

    por_letra = defaultdict(list)
    for it in items:
        por_letra[it["letra"]].append(it)
    letras = sorted(por_letra)
    print(f"Encontré {len(items)} imágenes en {len(letras)} letras: {', '.join(letras)}\n")

    random.seed(args.seed)
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    detector = crear_detector(args.confianza)

    aciertos = {m: defaultdict(int) for m in MODOS}
    totales = defaultdict(int)
    guardadas = defaultdict(int)

    for letra in letras:
        muestra = random.sample(por_letra[letra], min(args.muestras, len(por_letra[letra])))
        for it in muestra:
            img = leer_imagen(it["ruta"])
            if img is None:
                continue
            totales[letra] += 1
            for modo in MODOS:
                prep = preprocesar(img, modo, lado=args.lado)
                r = detectar_mano(detector, prep)
                if r:
                    aciertos[modo][letra] += 1
                    # guarda hasta 3 imágenes dibujadas por letra con el mejor modo
                    if modo == "resize+pad" and guardadas[letra] < 3:
                        nombre = f"{letra}_{guardadas[letra]}_{r['mano']}.jpg"
                        cv2.imwrite(str(salida / nombre), dibujar(prep, r["landmarks"]))
                        guardadas[letra] += 1

    # Tabla de resultados
    print(f"{'letra':<8}{'n':>4}" + "".join(f"{m:>14}" for m in MODOS))
    filas = []
    for letra in letras:
        n = totales[letra]
        if not n:
            continue
        pct = [100 * aciertos[m][letra] / n for m in MODOS]
        print(f"{letra:<8}{n:>4}" + "".join(f"{p:>13.0f}%" for p in pct))
        filas.append([letra, n] + [round(p, 1) for p in pct])
    n_total = sum(totales.values())
    if n_total:
        glob = [100 * sum(aciertos[m].values()) / n_total for m in MODOS]
        print(f"{'TOTAL':<8}{n_total:>4}" + "".join(f"{p:>13.0f}%" for p in glob))

    with open(salida / "resumen_deteccion.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["letra", "n"] + [f"pct_{m}" for m in MODOS])
        w.writerows(filas)
    print(f"\nImágenes con los puntos dibujados y resumen en: {salida.resolve()}")
    print("Abre esas imágenes y confirma que los puntos están bien puestos sobre la mano.")


if __name__ == "__main__":
    main()
