"""
PASOS 4 y 5: recorre TODO el dataset, extrae los landmarks con MediaPipe, los
normaliza y los guarda en un CSV (una fila por imagen donde se detectó mano).

Columnas: voluntario, letra, archivo, mano, score_mano, x0,y0,z0, ... x20,y20,z20
(el voluntario se guarda para poder dividir entrenamiento/prueba POR PERSONA).

Uso:
  python 02_extraer_landmarks.py --dataset data/LSC70ANH --layout voluntario/letra
  python 02_extraer_landmarks.py --dataset data/LSC70ANH --modo resize+pad --lado 480
"""
import argparse
import csv
from collections import defaultdict
from pathlib import Path

from landmarks_utils import (NOMBRES_COLUMNAS, crear_detector, detectar_mano,
                             leer_imagen, listar_imagenes, normalizar_landmarks,
                             preprocesar)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--layout", default="voluntario/letra",
                    choices=["voluntario/letra", "letra/voluntario"])
    ap.add_argument("--letras", nargs="*", help="solo estas letras (por defecto todas)")
    ap.add_argument("--modo", default="resize+pad",
                    choices=["original", "resize", "resize+pad"])
    ap.add_argument("--lado", type=int, default=480)
    ap.add_argument("--confianza", type=float, default=0.3)
    ap.add_argument("--salida", default="landmarks.csv")
    args = ap.parse_args()

    items = listar_imagenes(args.dataset, args.layout, args.letras)
    if not items:
        raise SystemExit("No encontré imágenes. Revisa --dataset y --layout.")
    print(f"{len(items)} imágenes a procesar...")

    detector = crear_detector(args.confianza)
    total = defaultdict(int)
    ok = defaultdict(int)
    raiz = Path(args.dataset)

    with open(args.salida, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["voluntario", "letra", "archivo", "mano", "score_mano"] + NOMBRES_COLUMNAS)
        for i, it in enumerate(items, 1):
            total[it["letra"]] += 1
            img = leer_imagen(it["ruta"])
            if img is not None:
                r = detectar_mano(detector, preprocesar(img, args.modo, lado=args.lado))
                if r:
                    try:
                        vec = normalizar_landmarks(r["puntos"], r["mano"])
                    except ValueError:
                        vec = None
                    if vec is not None:
                        ok[it["letra"]] += 1
                        w.writerow([it["voluntario"], it["letra"],
                                    str(it["ruta"].relative_to(raiz)),
                                    r["mano"], round(r["score"], 4)]
                                   + [round(float(v), 6) for v in vec])
            if i % 500 == 0:
                print(f"  {i}/{len(items)}")

    print(f"\nListo -> {args.salida}")
    print(f"{'letra':<8}{'total':>7}{'con mano':>10}{'%':>6}")
    for letra in sorted(total):
        t, k = total[letra], ok[letra]
        print(f"{letra:<8}{t:>7}{k:>10}{100 * k / t:>5.0f}%")
    print(f"{'TOTAL':<8}{sum(total.values()):>7}{sum(ok.values()):>10}"
          f"{100 * sum(ok.values()) / sum(total.values()):>5.0f}%")
    print("\nSi alguna letra queda con un % bajo, pruébala con LSC70AN (cuerpo completo) "
          "o con otro --modo / --confianza.")


if __name__ == "__main__":
    main()
