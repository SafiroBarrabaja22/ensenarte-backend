# ml/ — Entrenamiento del reconocedor del abecedario LSC

Scripts con los que se entrenó el clasificador que usa la **evaluación con
cámara**. El reconocimiento corre por completo en el navegador (MediaPipe Hands
+ KNN en JavaScript); el backend no ejecuta nada de esta carpeta ni recibe video.

> **Dónde vive el modelo exportado:** `modelo_knn.json` se versiona en el
> repositorio del frontend, en
> [`ensenarte-frontend/prueba-web/modelo_knn.json`](../../ensenarte-frontend/prueba-web/modelo_knn.json),
> junto a `lsc-reconocedor.js`, que lo carga. Aquí está en `.gitignore`: si lo
> reentrenas, copia el archivo generado a esa ruta del frontend.

## Contenido

| Archivo | Qué hace |
|---|---|
| `landmarks_utils.py` | Lectura de imágenes, detección con MediaPipe y normalización de los 21 puntos |
| `01_probar_deteccion.py` | Paso 3: % de imágenes con mano detectada por letra, con tres preprocesados; guarda ejemplos dibujados en `salida_prueba/` |
| `02_extraer_landmarks.py` | Pasos 4 y 5: recorre el dataset y genera `landmarks.csv` (63 valores normalizados por imagen) |
| `03_entrenar.py` | Pasos 6 a 8: entrena y evalúa el KNN dividiendo **por voluntario** y exporta `modelo_knn.json` |
| `04_comparar_modelos.py` | Paso 9: compara representaciones y modelos (KNN, SVM, MLP, regresión logística) con validación cruzada por voluntario |
| `05_ajustar_knn.py` | Paso 10: prueba qué muestras conviene poner en la base del KNN (cantidad, fotogramas, limpieza, rotaciones) sin cambiar el formato del modelo |
| `requirements.txt` | Dependencias de los scripts (independientes de las del backend) |

No se versionan (ver `.gitignore` de la raíz): `data/`, `*.csv`,
`salida_prueba/`, `modelo_knn.json`, `prueba-web/` y los entornos virtuales.

## Instalación

Python 3.9 a 3.12: `mediapipe==0.10.14` no publica ruedas para Python 3.13+.
Este entorno es **distinto** del `.venv` del backend.

```bash
cd ml
py -3.12 -m venv .venv            # Linux/Mac: python3.12 -m venv .venv
.venv\Scripts\activate            # Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
```

`cv2` (OpenCV) viene incluido con MediaPipe.

## Dataset

Se usa la parte **LSC70ANH** (recortes de la mano dominante, 120×120 px) del
dataset LSC70 de la Universidad del Cauca. Descárgalo de Mendeley Data y deja
las carpetas de las letras que se usan en `ml/data/LSC70ANH/<voluntario>/<letra>/`
(por ejemplo `data/LSC70ANH/Per01/A/Per01_A_0.jpg`).

Licencia: **CC BY 4.0**. Se puede usar, modificar y redistribuir, también con
fines comerciales, siempre que se cite a los autores y se indique si hubo
cambios. Cita:

> Muñoz Galindez, J. A., Villota Coral, L. V., & Vargas-Cañas, R. (2024).
> *Speak in Colombian Sign Language: A Dynamic LSC70 Database* (Versión 2)
> [Dataset]. Mendeley Data. https://doi.org/10.17632/9ssyn8tff5.2

> Muñoz Galindez, J. A., Villota Coral, L. V., & Vargas-Cañas, R. (2024).
> The dynamic Colombian sign language dataset for basic conversation LSC70.
> *Data in Brief*, 58, 111213. https://doi.org/10.1016/j.dib.2024.111213

Cambios hechos sobre el dataset: solo se usan las carpetas de letras; de cada
imagen se extraen los 21 puntos de la mano con MediaPipe y se normalizan (no se
redistribuyen imágenes).

## Cómo se entrenó

```bash
python 01_probar_deteccion.py  --dataset data/LSC70ANH --layout voluntario/letra
python 02_extraer_landmarks.py --dataset data/LSC70ANH --layout voluntario/letra
python 03_entrenar.py          --csv landmarks.csv --rotacion 15   # k=5, 150 muestras/letra
python 04_comparar_modelos.py  --csv landmarks.csv          # opcional
python 05_ajustar_knn.py       --csv landmarks.csv          # opcional
```

1. **Detección.** MediaPipe Hands detecta 21 puntos (x, y, z) por imagen. Las
   imágenes de 120 px se agrandan y se les añade margen (`resize+pad`, lado 480)
   porque así detecta más manos.
2. **Normalización** (la misma está replicada en `lsc-reconocedor.js`):
   1. coordenadas en píxeles (x·ancho, y·alto, z·ancho);
   2. restar la muñeca (punto 0);
   3. dividir entre la distancia 3D muñeca – base del dedo medio (punto 9);
   4. si MediaPipe dice `Left`, invertir el signo de x (todas quedan como `Right`).
3. **Entrenamiento.** KNN, k=5, distancia euclidiana, voto simple. Se excluyen
   letras con menos de 5 voluntarios (por eso `NN`, `S` y `Z` quedaron fuera). La
   evaluación separa entrenamiento y prueba **por persona** (`GroupShuffleSplit`),
   así que la precisión es sobre gente que el modelo no vio.
4. **Aumento por rotación** (`--rotacion 15`). A cada muestra se le añaden dos
   copias giradas ±15° en el plano de la imagen, alrededor de la muñeca. La
   rotación conserva la normalización, así que las copias son vectores válidos.
   Así el modelo tolera una mano un poco inclinada frente a la webcam.
5. **Exportación.** `modelo_knn.json` guarda 150 muestras de referencia por
   letra (repartidas entre voluntarios, originales y giradas), las 20 letras y
   la descripción de la normalización. La confianza que reporta el navegador es
   *votos de la letra ganadora / k* (0.2, 0.4, … 1.0).

### Resultados (modelo actual, 2026-10-10)

- 8 408 imágenes de los 70 voluntarios; MediaPipe detectó la mano en 8 270 (98 %).
- Corte 56 / 14 voluntarios: **89,6 %** de precisión con la base exportada
  (k=5, 150 muestras/letra, rotación ±15°).
- Validación cruzada por voluntario (`05_ajustar_knn.py`, 5 particiones),
  con la regla del frontend (letra correcta **y** confianza ≥ 0.6):

  | Base del KNN (150/letra) | Acierta | Acierta, mano girada 15° | Otra letra con confianza ≥ 0.6 |
  |---|---|---|---|
  | Sin rotación | 88,6 % | 82,0 % | 10,1 % |
  | **Con rotación ±15° (actual)** | **89,8 %** | **87,6 %** | **8,1 %** |

- Qué **no** ayudó (diferencias menores que el ruido entre particiones, ~1
  punto): usar solo los fotogramas finales de cada seña, limpiar muestras
  ruidosas (ENN) y ángulos entre 10° y 25° o combinados. Subir a 300
  muestras/letra gana ~0,3 puntos pero duplica el JSON (~2,5 MB).
- Comparando modelos (`04_comparar_modelos.py`), SVM, regresión logística y MLP
  llegan a ~91–93 %. Se mantuvo KNN porque es trivial de implementar en
  JavaScript sin dependencias; cambiarlo exige reescribir `lsc-reconocedor.js`.
- Letras más débiles: E (62 %), R (76 %), P (80 %).
  Confusiones típicas: E→C, P→N, R→F, O→C, R→V.

Versiones anteriores (archivos en `data/`, no versionados):

| Versión | Datos | Validación cruzada | Respaldo |
|---|---|---|---|
| 1 | 33 voluntarios | 83,7 % | `data/respaldo_33/` |
| 2 | 70 voluntarios | 89,1 % | `data/respaldo_70_sin_rotacion/` |
| 3 (actual) | 70 voluntarios + rotación ±15° | 90,5 % | — |

(Precisión sin umbral de confianza, KNN k=5, 150 muestras/letra.)

## Límites conocidos

- **Solo 20 letras:** A B C D E F I K L M N O P Q R T U V W Y. Faltan G, H, J,
  Ñ, S, X, Z y LL. Varias de ellas tienen movimiento, y el clasificador mira un
  solo cuadro, así que no puede reconocer señas dinámicas.
- **Solo la forma de la mano.** No usa movimiento, orientación respecto al
  cuerpo ni expresión facial, que también forman parte de la LSC.
- **Población limitada.** 70 voluntarios, todos jóvenes (18–29 años) y casi
  todos diestros.
- **Diferencias de dominio.** El entrenamiento usa recortes de 120 px de video
  frontal. Una webcam con otra luz, otro fondo, otra distancia o la mano
  parcialmente fuera de cuadro puede rendir peor que el ~90 % medido.
- **Espejo izquierda/derecha.** La etiqueta `Left`/`Right` de MediaPipe asume
  imagen tipo selfie. Si el video del navegador está en espejo, la mano puede
  salir invertida: hay que comprobarlo con la mano propia.
- **No es una herramienta de certificación.** El acierto lo decide el
  navegador; el servidor confía en lo que recibe. Sirve para practicar, no para
  evaluar formalmente a nadie.
