import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import fitz  # PyMuPDF
import os
import numpy as np
from paddleocr import PaddleOCR
import traceback # Para imprimir el stack trace completo en caso de error


class PDFOCRAnnotator:
    """
    Clase principal para la aplicación de anotación OCR de PDFs.
    Permite abrir un PDF, visualizar sus páginas, seleccionar regiones,
    realizar OCR en esas regiones usando PaddleOCR, y escribir el texto
    reconocido de vuelta en el PDF.
    """
    def __init__(self, root_window):
        """
        Inicializa la aplicación.
        Args:
            root_window (tk.Tk): La ventana principal de la aplicación.
        """
        self.root = root_window
        self.root.title("PDF OCR Annotator (PaddleOCR)")
        self.root.geometry("900x700") # Tamaño inicial de la ventana

        # Atributos relacionados con el documento PDF y su visualización
        self.pdf_document = None        # Objeto del documento PDF (PyMuPDF)
        self.current_page_num = 0       # Número de la página actual (basado en 0)
        self.current_pil_image = None   # Imagen de la página actual renderizada (Pillow)
        self.current_tk_image = None    # Imagen de la página actual para Tkinter (ImageTk)

        # Atributos para la selección de rectángulos en el canvas
        self.rect_start_x_canvas = None # Coordenada X inicial de la selección en el canvas
        self.rect_start_y_canvas = None # Coordenada Y inicial de la selección en el canvas
        self.current_rect_id = None     # ID del rectángulo visual dibujado en el canvas

        # Atributos de Zoom
        self.zoom_factor = 1.0          # Factor de zoom actual
        self.zoom_step = 0.1            # Incremento/decremento del zoom por paso
        self.min_zoom = 0.2             # Zoom mínimo permitido
        self.max_zoom = 5.0             # Zoom máximo permitido

        # Atributos de Panning (desplazamiento de la vista del PDF)
        self.pan_start_x_window = 0     # Coordenada X inicial del paneo (relativa a la ventana)
        self.pan_start_y_window = 0     # Coordenada Y inicial del paneo (relativa a la ventana)
        self.pan_sensitivity = 0.1      # Sensibilidad del movimiento de paneo
        self.is_panning = False         # Estado: True si se está paneando

        # Configuración e inicialización de PaddleOCR
        self.ocr_engine = None          # Motor OCR
        self.target_lang_ocr = 'es'     # Idioma para PaddleOCR (ej: 'es', 'en')
        self.ocr_model_version = 'PP-OCRv3' # Versión de los modelos de PaddleOCR
        self.initialize_paddleocr()

        # Configuración de la interfaz gráfica
        self._setup_ui()

    def _setup_ui(self):
        """Configura los frames, widgets y bindings de la interfaz gráfica."""
        # Frame para los controles (botones, etiqueta de página)
        controls_frame = tk.Frame(self.root)
        controls_frame.pack(pady=10)

        # Frame para el canvas donde se muestra el PDF
        self.canvas_frame = tk.Frame(self.root)
        self.canvas_frame.pack(fill=tk.BOTH, expand=True)

        # --- Controles ---
        self.btn_open = tk.Button(controls_frame, text="Abrir PDF", command=self.open_pdf)
        self.btn_open.pack(side=tk.LEFT, padx=5)

        self.btn_prev = tk.Button(controls_frame, text="Anterior", command=self.prev_page, state=tk.DISABLED)
        self.btn_prev.pack(side=tk.LEFT, padx=5)

        self.lbl_page = tk.Label(controls_frame, text="Página: -/-")
        self.lbl_page.pack(side=tk.LEFT, padx=5)

        self.btn_next = tk.Button(controls_frame, text="Siguiente", command=self.next_page, state=tk.DISABLED)
        self.btn_next.pack(side=tk.LEFT, padx=5)

        self.btn_save = tk.Button(controls_frame, text="Guardar PDF Modificado", command=self.save_pdf, state=tk.DISABLED)
        self.btn_save.pack(side=tk.LEFT, padx=5)

        # --- Canvas para mostrar el PDF ---
        self.canvas = tk.Canvas(self.canvas_frame, bg="lightgrey", cursor="arrow")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # --- Bindings de eventos del ratón en el canvas ---
        # Selección de rectángulo (Botón Izquierdo)
        self.canvas.bind("<ButtonPress-1>", self.on_mouse_press_selection)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag_selection)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_release_selection)

        # Zoom con rueda del ratón
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel_zoom)      # Windows, macOS, algunos Linux
        self.canvas.bind("<Button-4>", self.on_mouse_wheel_zoom)      # Linux (scroll up)
        self.canvas.bind("<Button-5>", self.on_mouse_wheel_zoom)      # Linux (scroll down)

        # Panning (Botón Derecho o Medio, según preferencia)
        self.canvas.bind("<ButtonPress-3>", self.on_mouse_press_pan)   # Usaremos Botón Derecho para pan
        self.canvas.bind("<B3-Motion>", self.on_mouse_drag_pan)
        self.canvas.bind("<ButtonRelease-3>", self.on_mouse_release_pan)

    def initialize_paddleocr(self):
        """Inicializa el motor PaddleOCR. Muestra errores si falla."""
        try:
            print(f"Intentando inicializar PaddleOCR con lang='{self.target_lang_ocr}', version='{self.ocr_model_version}'...")
            self.ocr_engine = PaddleOCR(
                use_angle_cls=True,         # Habilitar clasificación de ángulo del texto
                lang=self.target_lang_ocr,
                ocr_version=self.ocr_model_version)
            print(f"Motor PaddleOCR (lang='{self.target_lang_ocr}', version='{self.ocr_model_version}') parece inicializado.")
            
            # Realizar una prueba de OCR para asegurar que los modelos están listos y se descargan si es necesario.
            # cls=True es importante porque use_angle_cls=True en el constructor.
            print("Realizando prueba de OCR para 'calentar' los modelos...")
            _ = self.ocr_engine.ocr(np.zeros((100, 100, 3), dtype=np.uint8))
            print("Modelos de PaddleOCR (probablemente) descargados/cargados correctamente.")
        except Exception as e:
            user_home = os.path.expanduser('~')
            paddleocr_cache_dir = os.path.join(user_home, '.paddleocr')
            error_message = (
                f"No se pudo inicializar PaddleOCR: {e}\n\n"
                f"Idioma: '{self.target_lang_ocr}', Versión OCR: '{self.ocr_model_version}'.\n"
                "Asegúrese de tener 'paddlepaddle' y 'paddleocr' instalados y actualizados.\n"
                "La primera vez, necesita descargar modelos (requiere conexión a internet activa).\n\n"
                "POSIBLES SOLUCIONES:\n"
                "1. Verifique su conexión a internet.\n"
                f"2. Intente borrar la carpeta de modelos de PaddleOCR: '{paddleocr_cache_dir}' y reinicie la aplicación.\n"
                "3. Si 'use_gpu=True' está configurado en el código, asegúrese de que CUDA esté bien. Pruebe con 'use_gpu=False'.\n"
                f"4. Verifique que la versión de modelos OCR ('{self.ocr_model_version}') sea compatible con su instalación."
            )
            messagebox.showerror("Error de PaddleOCR", error_message)
            print(f"Error CRÍTICO al inicializar PaddleOCR: {e}")
            traceback.print_exc() # Imprimir stack trace para diagnóstico
            self.ocr_engine = None # Marcar el motor como no disponible


    def open_pdf(self):
        """Abre un archivo PDF seleccionado por el usuario."""
        filepath = filedialog.askopenfilename(
            title="Seleccionar archivo PDF",
            filetypes=(("Archivos PDF", "*.pdf"), ("Todos los archivos", "*.*"))
        )
        if not filepath: # Si el usuario cancela la selección
            return
        
        try:
            if self.pdf_document: # Cerrar PDF anterior si lo hubiera
                self.pdf_document.close()
            
            self.pdf_document = fitz.open(filepath)
            self.current_page_num = 0    # Ir a la primera página
            self.zoom_factor = 1.0       # Resetear zoom
            self.canvas.xview_moveto(0)  # Resetear scroll horizontal
            self.canvas.yview_moveto(0)  # Resetear scroll vertical
            
            self.display_page()          # Mostrar la primera página
            self.update_page_controls_state() # Actualizar estado de botones de navegación
            self.btn_save.config(state=tk.NORMAL) # Habilitar botón de guardar
        except Exception as e:
            messagebox.showerror("Error al Abrir PDF", f"No se pudo abrir el archivo PDF:\n{e}")
            traceback.print_exc()
            self.pdf_document = None
            self.current_pil_image = None
            self.canvas.delete("all")
            self.update_page_controls_state()
            self.btn_save.config(state=tk.DISABLED)

    def display_page(self):
        """Renderiza y muestra la página actual del PDF en el canvas."""
        if not self.pdf_document or \
           not (0 <= self.current_page_num < self.pdf_document.page_count):
            self.canvas.delete("all")
            self.current_pil_image = None
            self.current_tk_image = None
            zoom_text = f"(Zoom: {self.zoom_factor:.0%})" if self.pdf_document else ""
            self.lbl_page.config(text=f"Página: -/- {zoom_text}")
            return

        try:
            page = self.pdf_document.load_page(self.current_page_num)
            # Crear matriz de transformación para el zoom
            mat = fitz.Matrix(self.zoom_factor, self.zoom_factor)
            # Renderizar la página como pixmap (imagen rasterizada)
            pix = page.get_pixmap(matrix=mat, alpha=False) # alpha=False para RGB

            # Convertir pixmap a imagen Pillow, luego a imagen Tkinter
            self.current_pil_image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            self.current_tk_image = ImageTk.PhotoImage(self.current_pil_image)

            self.canvas.delete("all") # Limpiar canvas antes de redibujar
            # Configurar la región de scroll del canvas al tamaño de la imagen renderizada
            self.canvas.config(scrollregion=(0, 0, self.current_tk_image.width(), self.current_tk_image.height()))
            # Dibujar la imagen de la página en el canvas
            self.canvas.create_image(0, 0, anchor=tk.NW, image=self.current_tk_image)

            self.lbl_page.config(text=f"Página: {self.current_page_num + 1}/{self.pdf_document.page_count} (Zoom: {self.zoom_factor:.0%})")
        except Exception as e:
            messagebox.showerror("Error al Mostrar Página", f"Error al mostrar la página {self.current_page_num + 1}:\n{e}")
            traceback.print_exc()
            self.current_pil_image = None
            self.current_tk_image = None
            self.canvas.delete("all")
            self.lbl_page.config(text=f"Error (Pág: {self.current_page_num+1}, Zoom: {self.zoom_factor:.0%})")

    def on_mouse_wheel_zoom(self, event):
        """Maneja el evento de la rueda del ratón para hacer zoom centrado en el cursor."""
        if not self.pdf_document or not self.current_pil_image:
            return

        if self.current_rect_id: # Si hay una selección activa, cancelarla al hacer zoom
            self.canvas.delete(self.current_rect_id)
            self.current_rect_id = None
            self.rect_start_x_canvas = None # Resetear inicio de selección

        # Determinar dirección del scroll
        scroll_direction = 0
        if event.num == 4:  # Linux scroll up
            scroll_direction = 1
        elif event.num == 5:  # Linux scroll down
            scroll_direction = -1
        elif hasattr(event, 'delta') and event.delta != 0:  # Windows, macOS
            scroll_direction = 1 if event.delta > 0 else -1
        
        if scroll_direction == 0: # No scroll detectado
            return

        old_zoom_factor = self.zoom_factor
        # Aplicar cambio de zoom
        if scroll_direction > 0:
            self.zoom_factor *= (1 + self.zoom_step)
        else:
            self.zoom_factor /= (1 + self.zoom_step)
        # Limitar el zoom a los valores min/max
        self.zoom_factor = max(self.min_zoom, min(self.max_zoom, self.zoom_factor))

        if abs(self.zoom_factor - old_zoom_factor) < 0.0001: # Si el cambio es insignificante
            self.zoom_factor = old_zoom_factor # Revertir para evitar recálculos
            return

        # --- Lógica para zoom centrado en el cursor ---
        # Coordenadas del cursor en el canvas (relativas a la imagen con zoom *antes* del nuevo zoom)
        canvas_x_at_cursor_before_zoom = self.canvas.canvasx(event.x)
        canvas_y_at_cursor_before_zoom = self.canvas.canvasy(event.y)
        
        # Punto correspondiente en el documento PDF original (coordenadas sin zoom)
        doc_x_at_cursor = canvas_x_at_cursor_before_zoom / old_zoom_factor
        doc_y_at_cursor = canvas_y_at_cursor_before_zoom / old_zoom_factor
        
        # Redibujar la página con el nuevo factor de zoom
        self.display_page() 
        if not self.current_tk_image: return # Salir si display_page falló

        img_width_after_zoom, img_height_after_zoom = self.current_tk_image.width(), self.current_tk_image.height()
        if img_width_after_zoom == 0 or img_height_after_zoom == 0: return

        # Coordenadas donde el punto del documento (doc_x_at_cursor, doc_y_at_cursor) 
        # debería estar en la nueva imagen reescalada (con el nuevo zoom_factor)
        canvas_x_of_doc_point_after_zoom = doc_x_at_cursor * self.zoom_factor
        canvas_y_of_doc_point_after_zoom = doc_y_at_cursor * self.zoom_factor
        
        # Calcular el desplazamiento necesario en píxeles para que el punto del documento
        # bajo el cursor (event.x, event.y en coords de ventana) permanezca allí visualmente.
        # Queremos que: canvas_x_of_doc_point_after_zoom - scroll_offset_x_pixels = event.x (coordenada de ventana)
        scroll_offset_x_pixels = canvas_x_of_doc_point_after_zoom - event.x
        scroll_offset_y_pixels = canvas_y_of_doc_point_after_zoom - event.y

        # Convertir el desplazamiento en píxeles a fracciones para xview_moveto / yview_moveto
        # (frac_x es la fracción del ancho total de la imagen que debe estar a la izquierda del viewport)
        frac_x = scroll_offset_x_pixels / img_width_after_zoom
        frac_y = scroll_offset_y_pixels / img_height_after_zoom
        
        # Mover la vista del canvas para centrar el zoom
        self.canvas.xview_moveto(max(0, min(1, frac_x)))
        self.canvas.yview_moveto(max(0, min(1, frac_y)))
            
        self.lbl_page.config(text=f"Página: {self.current_page_num + 1}/{self.pdf_document.page_count} (Zoom: {self.zoom_factor:.0%})")

    def update_page_controls_state(self):
        """Actualiza el estado (habilitado/deshabilitado) de los botones de navegación y guardado."""
        if not self.pdf_document:
            self.btn_prev.config(state=tk.DISABLED)
            self.btn_next.config(state=tk.DISABLED)
            self.btn_save.config(state=tk.DISABLED)
            self.lbl_page.config(text="Página: -/-")
            return

        self.btn_prev.config(state=tk.NORMAL if self.current_page_num > 0 else tk.DISABLED)
        self.btn_next.config(state=tk.NORMAL if self.current_page_num < self.pdf_document.page_count - 1 else tk.DISABLED)
        # El estado de btn_save se maneja en open_pdf y cuando se realizan cambios.
        self.lbl_page.config(text=f"Página: {self.current_page_num + 1}/{self.pdf_document.page_count} (Zoom: {self.zoom_factor:.0%})")

    def prev_page(self):
        """Va a la página anterior del PDF."""
        if self.pdf_document and self.current_page_num > 0:
            self.current_page_num -= 1
            self.canvas.xview_moveto(0) # Resetear scroll al cambiar de página
            self.canvas.yview_moveto(0)
            self.display_page()
            self.update_page_controls_state()

    def next_page(self):
        """Va a la página siguiente del PDF."""
        if self.pdf_document and self.current_page_num < self.pdf_document.page_count - 1:
            self.current_page_num += 1
            self.canvas.xview_moveto(0) # Resetear scroll al cambiar de página
            self.canvas.yview_moveto(0)
            self.display_page()
            self.update_page_controls_state()

    # --- Métodos para Selección de Rectángulo (Botón Izquierdo del Ratón) ---
    def on_mouse_press_selection(self, event):
        """Inicia la selección de un rectángulo cuando se presiona el botón izquierdo."""
        if not self.current_pil_image or self.is_panning: # No permitir selección si no hay imagen o se está paneando
            return
        
        if self.current_rect_id: # Borrar rectángulo de selección anterior si existe
            self.canvas.delete(self.current_rect_id)

        # Guardar coordenadas de inicio en el canvas (ya tienen en cuenta el scroll y zoom)
        self.rect_start_x_canvas = self.canvas.canvasx(event.x)
        self.rect_start_y_canvas = self.canvas.canvasy(event.y)
        
        # Crear un rectángulo visual inicial de tamaño cero
        self.current_rect_id = self.canvas.create_rectangle(
            self.rect_start_x_canvas, self.rect_start_y_canvas,
            self.rect_start_x_canvas, self.rect_start_y_canvas,
            outline="red", width=2
        )

    def on_mouse_drag_selection(self, event):
        """Actualiza el tamaño del rectángulo de selección mientras se arrastra el ratón."""
        if not self.current_pil_image or self.rect_start_x_canvas is None or \
           not self.current_rect_id or self.is_panning:
            return
        
        # Obtener coordenadas actuales del cursor en el canvas
        cur_x_canvas = self.canvas.canvasx(event.x)
        cur_y_canvas = self.canvas.canvasy(event.y)
        
        # Actualizar las coordenadas del rectángulo visual
        self.canvas.coords(self.current_rect_id, 
                           self.rect_start_x_canvas, self.rect_start_y_canvas, 
                           cur_x_canvas, cur_y_canvas)

    def on_mouse_release_selection(self, event):
        """Finaliza la selección del rectángulo y procesa el área seleccionada para OCR."""
        if self.is_panning: # Si fue un evento de paneo, ignorar
            return 
        
        if not self.current_pil_image or self.rect_start_x_canvas is None or not self.current_rect_id:
            if self.current_rect_id: # Limpiar si algo quedó mal
                self.canvas.delete(self.current_rect_id)
            self.current_rect_id = None
            self.rect_start_x_canvas = None
            return

        # Obtener coordenadas finales del cursor en el canvas
        rect_end_x_canvas = self.canvas.canvasx(event.x)
        rect_end_y_canvas = self.canvas.canvasy(event.y)

        # Eliminar el rectángulo visual del canvas
        self.canvas.delete(self.current_rect_id)
        self.current_rect_id = None

        # Normalizar coordenadas (x0 < x1, y0 < y1)
        x0_canvas = int(min(self.rect_start_x_canvas, rect_end_x_canvas))
        y0_canvas = int(min(self.rect_start_y_canvas, rect_end_y_canvas))
        x1_canvas = int(max(self.rect_start_x_canvas, rect_end_x_canvas))
        y1_canvas = int(max(self.rect_start_y_canvas, rect_end_y_canvas))

        # Resetear coordenadas de inicio para la próxima selección
        self.rect_start_x_canvas = None 

        # Ignorar selecciones muy pequeñas
        if abs(x1_canvas - x0_canvas) < 5 or abs(y1_canvas - y0_canvas) < 5:
            # print("Selección muy pequeña, ignorada.") # Comentario informativo
            return

        # Las coordenadas (x0_canvas, y0_canvas, x1_canvas, y1_canvas) son relativas
        # a la imagen renderizada en el canvas (self.current_pil_image), que ya tiene el zoom aplicado.
        selection_box_canvas_coords = (x0_canvas, y0_canvas, x1_canvas, y1_canvas)
        
        # Llamar a la función que realiza el OCR y la anotación
        self.perform_ocr_and_annotate(selection_box_canvas_coords)


    # --- Métodos para Panning (Desplazamiento con Botón Derecho del Ratón) ---
    def on_mouse_press_pan(self, event):
        """Inicia el modo de paneo cuando se presiona el botón derecho."""
        if not self.current_pil_image:
            return
        
        # Si hay una selección de rectángulo activa, cancelarla
        if self.current_rect_id: 
            self.canvas.delete(self.current_rect_id)
            self.current_rect_id = None
            self.rect_start_x_canvas = None # Resetear
            
        self.is_panning = True
        # Guardar coordenadas de inicio del paneo (relativas a la ventana del canvas)
        self.pan_start_x_window = event.x 
        self.pan_start_y_window = event.y
        self.canvas.config(cursor="fleur") # Cambiar cursor a "fleur" para indicar paneo

    def on_mouse_drag_pan(self, event):
        """Desplaza la vista del canvas mientras se arrastra el ratón en modo paneo."""
        if not self.is_panning or not self.current_pil_image:
            return
        
        # Calcular delta de movimiento en coordenadas de ventana
        dx_window = event.x - self.pan_start_x_window
        dy_window = event.y - self.pan_start_y_window
        
        # Desplazar la vista del canvas.
        # El scroll es en "unidades" del canvas. La sensibilidad ajusta la velocidad.
        # El signo negativo es para que el contenido se mueva en la misma dirección que el ratón.
        self.canvas.xview_scroll(int(-dx_window * self.pan_sensitivity), "units")
        self.canvas.yview_scroll(int(-dy_window * self.pan_sensitivity), "units")
        
        # Actualizar coordenadas de inicio para el siguiente movimiento delta
        self.pan_start_x_window = event.x 
        self.pan_start_y_window = event.y

    def on_mouse_release_pan(self, event):
        """Finaliza el modo de paneo."""
        if not self.is_panning: # Puede ocurrir si el release es fuera de un press iniciado
            return
        self.is_panning = False
        self.canvas.config(cursor="arrow") # Restaurar cursor por defecto


    def perform_ocr_and_annotate(self, canvas_coords):
        """
        Realiza OCR en la región especificada por `canvas_coords` y anota el PDF.
        Args:
            canvas_coords (tuple): (x0, y0, x1, y1) coordenadas de la selección en el
                                   canvas (relativas a la imagen con zoom).
        """
        if not self.current_pil_image:
            messagebox.showwarning("Advertencia OCR", "No hay imagen cargada para realizar OCR.")
            return
        if not self.ocr_engine:
            messagebox.showerror("Error OCR", "El motor OCR (PaddleOCR) no está inicializado.")
            return

        try:
            # 1. Recortar la porción de la imagen del canvas (self.current_pil_image)
            #    Las canvas_coords ya están validadas (tamaño mínimo) y normalizadas.
            #    Asegurarse de que las coordenadas de recorte estén dentro de los límites de la imagen.
            img_w, img_h = self.current_pil_image.size
            crop_x0 = max(0, canvas_coords[0])
            crop_y0 = max(0, canvas_coords[1])
            crop_x1 = min(img_w, canvas_coords[2])
            crop_y1 = min(img_h, canvas_coords[3])

            if not (crop_x1 > crop_x0 and crop_y1 > crop_y0): # Chequeo adicional
                # print("Área de selección inválida después del clamping.")
                return
                
            cropped_pil_image_for_ocr = self.current_pil_image.crop((crop_x0, crop_y0, crop_x1, crop_y1))
            
            # 2. Realizar OCR en la imagen recortada
            cropped_numpy_image = np.array(cropped_pil_image_for_ocr)
            # Usar cls=True porque use_angle_cls=True en el constructor de PaddleOCR
            ocr_result = self.ocr_engine.ocr(cropped_numpy_image)

            # 3. Extraer el texto reconocido
            ocr_text_parts = []
            # Estructura de ocr_result: [[line1_info, line2_info, ...]]
            # line_info: [bounding_box_dentro_del_crop, (text, confidence_score)]
            if ocr_result and ocr_result[0] is not None: # ocr_result[0] contiene la lista de líneas para la imagen
                for line_info in ocr_result[0]:
                    ocr_text_parts.append(line_info[1][0]) # Extraer solo el texto
            
            ocr_text = "\n".join(ocr_text_parts).strip()
            # print(f"Texto OCR para anotación: '{ocr_text}'") # Log informativo

            if not ocr_text:
                messagebox.showinfo("Resultado OCR", "No se detectó texto en la selección.")
                return

            # 4. Convertir coordenadas del canvas a coordenadas del PDF original (sin zoom)
            #    Las canvas_coords son de la imagen que ya tiene el zoom aplicado.
            pdf_x0 = canvas_coords[0] / self.zoom_factor
            pdf_y0 = canvas_coords[1] / self.zoom_factor
            pdf_x1 = canvas_coords[2] / self.zoom_factor
            pdf_y1 = canvas_coords[3] / self.zoom_factor
            
            fitz_rect_pdf = fitz.Rect(pdf_x0, pdf_y0, pdf_x1, pdf_y1)
            
            # 5. Anotar el PDF
            page = self.pdf_document.load_page(self.current_page_num)
            
            # 5a. Dibujar un rectángulo blanco para cubrir el contenido original
            page.draw_rect(fitz_rect_pdf, color=(1, 1, 1), fill=(1, 1, 1), overlay=True)
            
            # 5b. Calcular tamaño de fuente dinámicamente (aproximado)
            rect_height_pt_pdf = fitz_rect_pdf.height # Altura del rectángulo en puntos PDF
            font_size = max(4, min(12, int(rect_height_pt_pdf * 0.7))) # Ajustar multiplicador 0.7 si es necesario
            if rect_height_pt_pdf < 6: # Para rectángulos muy pequeños
                font_size = max(2, int(rect_height_pt_pdf * 0.8))
            
            # 5c. Insertar el texto OCR en el PDF
            #      'helv' es Helvetica. Para caracteres especiales/otros idiomas, se podría necesitar otra fuente.
            return_code = page.insert_textbox(fitz_rect_pdf, ocr_text,
                                              fontsize=font_size, fontname="helv",
                                              color=(0, 0, 0), align=fitz.TEXT_ALIGN_LEFT,
                                              rotate=0, overlay=True)
            if return_code < 0:
                # Advierte si el texto no cupo completamente. rc es la cantidad de texto que no cupo.
                print(f"Advertencia: El texto OCR ('{ocr_text[:20]}...') puede no caber completamente. Código PyMuPDF: {return_code}")

            # 6. Refrescar la visualización del PDF en el canvas para mostrar los cambios
            #    Guardar la posición actual del scroll para restaurarla.
            current_xview_frac = self.canvas.xview()[0] # Fracción de scroll horizontal
            current_yview_frac = self.canvas.yview()[0] # Fracción de scroll vertical
            
            self.display_page() # Redibuja la página, mostrando la anotación
            
            # Restaurar la vista del canvas a donde estaba
            self.canvas.xview_moveto(current_xview_frac)
            self.canvas.yview_moveto(current_yview_frac)

        except Exception as e:
            messagebox.showerror("Error en OCR/Anotación", f"Ocurrió un error:\n{e}\nTipo: {type(e)}")
            traceback.print_exc()
            # Intentar restaurar la vista incluso si hay error
            try:
                current_xview_frac = self.canvas.xview()[0]
                current_yview_frac = self.canvas.yview()[0]
                self.display_page()
                self.canvas.xview_moveto(current_xview_frac)
                self.canvas.yview_moveto(current_yview_frac)
            except Exception as e_restore:
                print(f"Error adicional al intentar restaurar la vista después de un error de anotación: {e_restore}")


    def save_pdf(self):
        """Guarda el PDF modificado en un archivo nuevo."""
        if not self.pdf_document:
            messagebox.showwarning("Guardar PDF", "No hay ningún PDF cargado para guardar.")
            return
        
        filepath = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=(("Archivos PDF", "*.pdf"), ("Todos los archivos", "*.*")),
            title="Guardar PDF modificado como..."
        )
        if not filepath: # Si el usuario cancela
            return
        
        try:
            # Opciones de guardado para optimizar el PDF:
            # garbage: recolectar objetos no referenciados (0-4, mayor es más agresivo)
            # deflate: comprimir streams
            # clean: limpiar y sanear la sintaxis del PDF
            self.pdf_document.save(filepath, garbage=3, deflate=True, clean=True)
            messagebox.showinfo("Guardado Exitoso", f"PDF modificado guardado en:\n{filepath}")
        except Exception as e:
            messagebox.showerror("Error al Guardar PDF", f"No se pudo guardar el PDF:\n{e}")
            traceback.print_exc()

# --- INICIO DE LA APLICACIÓN ---
if __name__ == "__main__":
    print("Iniciando aplicación PDF OCR Annotator con PaddleOCR...")
    # La configuración de idioma y versión de OCR se establece en PDFOCRAnnotator.__init__
    # y se imprime durante la inicialización de PaddleOCR.

    root = tk.Tk()  # Crear la ventana principal de Tkinter
    app = PDFOCRAnnotator(root) # Crear una instancia de la aplicación

    # Comprobar si el motor OCR se inicializó correctamente
    if app.ocr_engine is None:
        # El mensaje de error ya se mostró desde initialize_paddleocr
        print("ADVERTENCIA: El motor OCR no se pudo inicializar. La funcionalidad OCR no estará disponible.")
        # Se podría optar por cerrar la app si OCR es esencial:
        # root.destroy()
    
    root.mainloop() # Iniciar el bucle de eventos de Tkinter