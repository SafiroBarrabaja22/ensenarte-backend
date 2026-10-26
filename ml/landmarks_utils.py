"""
Utilidades compartidas por los scripts de LSC (lengua de señas colombiana).

IMPORTANTE: la función `normalizar_landmarks` es la que después hay que portar
EXACTAMENTE igual a JavaScript para la evaluación en el navegador. Si el
entrenamiento y el navegador normalizan distinto, el modelo falla sin dar error.
"""
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np

EXTENSIONES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

# Índices de MediaPipe Hands
MUNECA = 0
BASE_DEDO_MEDIO = 9


# ---------------------------------------------------------------------------
# Lectura de imágenes y recorrido del dataset
# ---------------------------------------------------------------------------
def leer_imagen(ruta):
    """Lee una imagen en BGR. Usa imdecode para que funcione con tildes/ñ en Windows."""
    datos = np.fromfile(str(ruta), dtype=np.uint8)
    if datos.size == 0:
        return None
    return cv2.imdecode(datos, cv2.IMREAD_COLOR)


def listar_imagenes(raiz, layout="voluntario/letra", letras=None):
    """
    Recorre `raiz` y devuelve una lista de dicts: {ruta, voluntario, letra}.

    layout:
      "voluntario/letra" -> raiz/<voluntario>/<letra>/imagen.jpg
      "letra/voluntario" -> raiz/<letra>/<voluntario>/imagen.jpg
    Si las imágenes están directamente dentro de una carpeta de letra
    (raiz/<letra>/imagen.jpg), el voluntario queda como "desconocido".
    """
    raiz = Path(raiz)
    filtro = {l.lower() for l in letras} if letras else None
    items = []
    for ruta in sorted(raiz.rglob("*")):
        if ruta.suffix.lower() not in EXTENSIONES or not ruta.is_file():
            continue
        carpetas = ruta.relative_to(raiz).parts[:-1]
        if len(carpetas) >= 2:
            if layout == "voluntario/letra":
                voluntario, letra = carpetas[0], carpetas[1]
            else:
                letra, voluntario = carpetas[0], carpetas[1]
        elif len(carpetas) == 1:
            letra, voluntario = carpetas[0], "desconocido"
        else:
            continue
        if filtro and letra.lower() not in filtro:
            continue
        items.append({"ruta": ruta, "voluntario": voluntario, "letra": letra})
    return items


# ---------------------------------------------------------------------------
# Preprocesado: agrandar + margen (las imágenes de 120x120 son muy pequeñas)
# ---------------------------------------------------------------------------
def preprocesar(img_bgr, modo="resize+pad", lado=480, margen=0.25):
    """
    modo:
      "original"   -> sin tocar
      "resize"     -> agranda para que el lado mayor mida `lado` px
      "resize+pad" -> agranda y agrega un margen (fracción `margen` por cada lado)
    """
    if modo == "original":
        return img_bgr
    h, w = img_bgr.shape[:2]
    escala = lado / max(h, w)
    interp = cv2.INTER_CUBIC if escala > 1 else cv2.INTER_AREA
    img = cv2.resize(img_bgr, (int(round(w * escala)), int(round(h * escala))), interpolation=interp)
    if modo == "resize":
        return img
    # resize+pad: el margen se rellena con el color mediano de la imagen (no con espejo,
    # para no crear "manos fantasma" duplicadas)
    color = [int(c) for c in np.median(img.reshape(-1, 3), axis=0)]
    m = int(round(max(img.shape[:2]) * margen))
    return cv2.copyMakeBorder(img, m, m, m, m, cv2.BORDER_CONSTANT, value=color)


# ---------------------------------------------------------------------------
# Detección con MediaPipe
# ---------------------------------------------------------------------------
def crear_detector(min_confianza=0.3, modelo=1):
    """Detector para fotos sueltas (static_image_mode=True) y una sola mano."""
    return mp.solutions.hands.Hands(
        static_image_mode=True,
        max_num_hands=1,
        model_complexity=modelo,
        min_detection_confidence=min_confianza,
    )


def detectar_mano(detector, img_bgr):
    """
    Devuelve None si no hay mano, o un dict:
      {puntos: array (21,3) en PÍXELES (x*ancho, y*alto, z*ancho),
       mano: "Left"/"Right" (etiqueta de MediaPipe),
       score: confianza de la etiqueta,
       landmarks: objeto original, para dibujar}
    """
    h, w = img_bgr.shape[:2]
    res = detector.process(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB))
    if not res.multi_hand_landmarks:
        return None
    lm = res.multi_hand_landmarks[0]
    clase = res.multi_handedness[0].classification[0]
    puntos = np.array([[p.x * w, p.y * h, p.z * w] for p in lm.landmark], dtype=np.float64)
    return {"puntos": puntos, "mano": clase.label, "score": float(clase.score), "landmarks": lm}


def dibujar(img_bgr, landmarks):
    """Devuelve una copia con los puntos de la mano dibujados (para revisar a ojo)."""
    salida = img_bgr.copy()
    mp.solutions.drawing_utils.draw_landmarks(
        salida, landmarks, mp.solutions.hands.HAND_CONNECTIONS
    )
    return salida


# ---------------------------------------------------------------------------
# Paso 5: normalización  (PORTAR IGUAL A JAVASCRIPT)
# ---------------------------------------------------------------------------
def normalizar_landmarks(puntos, mano, unificar_mano=True):
    """
    puntos: array (21, 3) en píxeles (x*ancho, y*alto, z*ancho).
    mano:   "Left" o "Right" según MediaPipe.

    1. Traslada: la muñeca (punto 0) queda en el origen.
    2. Escala: divide entre la distancia 3D muñeca -> base del dedo medio (punto 9),
       para que no importe qué tan cerca está la mano de la cámara.
    3. Unifica la mano: si es "Left", invierte el signo de x, de modo que todas las
       manos queden como si fueran "Right".
    Devuelve un vector plano de 63 números (x0,y0,z0,x1,y1,z1,...).
    """
    p = np.asarray(puntos, dtype=np.float64).copy()
    p -= p[MUNECA]
    escala = np.linalg.norm(p[BASE_DEDO_MEDIO])
    if escala < 1e-6:
        raise ValueError("Escala casi cero: landmarks degenerados")
    p /= escala
    if unificar_mano and mano == "Left":
        p[:, 0] *= -1.0
    return p.reshape(-1)


NOMBRES_COLUMNAS = [f"{eje}{i}" for i in range(21) for eje in ("x", "y", "z")]
