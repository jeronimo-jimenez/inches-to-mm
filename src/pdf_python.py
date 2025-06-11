import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import fitz  # PyMuPDF
import os
import numpy as np
from paddleocr import PaddleOCR
import traceback # Añadido para depuración

# --- CLASE PRINCIPAL DE LA APLICACIÓN ---
class PDFOCRAnnotator:
    def __init__(self, root):
        self.root = root
        self.root.title("PDF OCR Annotator (PaddleOCR)")
        self.root.geometry("900x700")

        self.pdf_document = None
        self.current_page_num = 0
        self.current_pil_image = None # Imagen renderizada con zoom actual
        self.current_tk_image = None
        
        # Coordenadas de inicio de selección en el canvas (relativas a la imagen con zoom)
        self.rect_start_x_canvas = None # Renombrado para claridad
        self.rect_start_y_canvas = None # Renombrado para claridad
        self.current_rect_id = None # ID del rectángulo visual en el canvas

        # --- Atributos de Zoom ---
        self.zoom_factor = 1.0
        self.zoom_step = 0.1
        self.min_zoom = 0.2
        self.max_zoom = 5.0

        # --- Atributos de Panning (desplazamiento) ---
        self.pan_start_x_window = 0 # Coordenadas de ventana para paneo
        self.pan_start_y_window = 0
        self.sensitivity = 0.3 # Sensibilidad del paneo
        self.is_panning = False

        # --- Inicializar PaddleOCR ---
        self.ocr_engine = None
        self.target_lang_ocr = 'en'
        self.ocr_model_version = 'PP-OCRv5' # O la versión que uses
        self.initialize_paddleocr()

        self.inital_pan_scroll_xfrac = 0.0
        self.inital_pan_scroll_yfrac = 0.0


        # --- Frames ---
        controls_frame = tk.Frame(root)
        controls_frame.pack(pady=10)

        self.canvas_frame = tk.Frame(root)
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

        # --- Canvas ---
        self.canvas = tk.Canvas(self.canvas_frame, bg="lightgrey", cursor="arrow")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.canvas.bind("<ButtonPress-1>", self.on_mouse_press)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_release)
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel)
        self.canvas.bind("<Button-4>", self.on_mouse_wheel) # Linux scroll up
        self.canvas.bind("<Button-5>", self.on_mouse_wheel) # Linux scroll down
        self.canvas.bind("<ButtonPress-3>", self.on_pan_press) # Pan con botón derecho
        self.canvas.bind("<B3-Motion>", self.on_pan_motion)
        self.canvas.bind("<ButtonRelease-3>", self.on_pan_release)

    def initialize_paddleocr(self):
        try:
            print(f"Intentando inicializar PaddleOCR con lang='{self.target_lang_ocr}', version='{self.ocr_model_version}'...")
            self.ocr_engine = PaddleOCR(
                use_angle_cls=True,
                lang=self.target_lang_ocr,
                ocr_version=self.ocr_model_version
            )
            print(f"Motor PaddleOCR (lang='{self.target_lang_ocr}', version='{self.ocr_model_version}') parece inicializado.")
            print("Realizando prueba de OCR para asegurar que los modelos están listos...")
            # Usar ocr() con cls=True porque use_angle_cls=True en el constructor.
            _ = self.ocr_engine.predict(np.zeros((100, 100, 3), dtype=np.uint8)) 
            print("Modelos de PaddleOCR (probablemente) descargados/cargados correctamente.")
        except Exception as e:
            user_home = os.path.expanduser('~')
            paddleocr_cache_dir = os.path.join(user_home, '.paddleocr')
            error_message = (
                f"No se pudo inicializar PaddleOCR: {e}\n\n"
                f"Idioma intentado: '{self.target_lang_ocr}', Versión OCR: '{self.ocr_model_version}'.\n"
                "Asegúrate de tener 'paddlepaddle' y 'paddleocr' instalados y actualizados.\n"
                "La primera vez, necesita descargar modelos (requiere conexión a internet activa).\n\n"
                "POSIBLES SOLUCIONES:\n"
                "1. Verifica tu conexión a internet.\n"
                f"2. Intenta borrar la carpeta de modelos de PaddleOCR: '{paddleocr_cache_dir}' y reinicia.\n"
                "3. Si 'use_gpu=True', verifica CUDA. Prueba con 'use_gpu=False'.\n"
                f"4. Verifica que la versión de modelos OCR ('{self.ocr_model_version}') sea compatible."
            )
            messagebox.showerror("Error de PaddleOCR", error_message)
            print(f"Error CRÍTICO al inicializar PaddleOCR: {e}")
            traceback.print_exc()
            self.ocr_engine = None


    def open_pdf(self):
        filepath = filedialog.askopenfilename(
            title="Seleccionar archivo PDF",
            filetypes=(("Archivos PDF", "*.pdf"), ("Todos los archivos", "*.*"))
        )
        if not filepath: return
        try:
            if self.pdf_document: self.pdf_document.close()
            self.pdf_document = fitz.open(filepath)
            self.current_page_num = 0
            self.zoom_factor = 1.0
            self.canvas.xview_moveto(0) # Resetear vista horizontal del canvas
            self.canvas.yview_moveto(0) # Resetear vista vertical del canvas
            self.display_page()
            self.update_page_controls()
            self.btn_save.config(state=tk.NORMAL)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo abrir el PDF: {e}")
            self.pdf_document = None; self.current_pil_image = None
            self.canvas.delete("all"); self.update_page_controls()
            self.btn_save.config(state=tk.DISABLED)

    def display_page(self):
        if not self.pdf_document or not (0 <= self.current_page_num < self.pdf_document.page_count):
            self.canvas.delete("all"); self.current_pil_image = None; self.current_tk_image = None
            zoom_text = f"(Zoom: {self.zoom_factor:.0%})" if self.pdf_document else ""
            self.lbl_page.config(text=f"Página: -/- {zoom_text}")
            return
        try:
            page = self.pdf_document.load_page(self.current_page_num)
            mat = fitz.Matrix(self.zoom_factor, self.zoom_factor) # Matriz de transformación para el zoom
            pix = page.get_pixmap(matrix=mat, alpha=False) # Renderizar página con zoom
            self.current_pil_image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            self.current_tk_image = ImageTk.PhotoImage(self.current_pil_image)
            self.canvas.delete("all") # Limpiar canvas
            # Configurar scrollregion al tamaño de la imagen renderizada (con zoom)
            self.canvas.config(scrollregion=(0, 0, self.current_tk_image.width(), self.current_tk_image.height()))
            self.canvas.create_image(0, 0, anchor=tk.NW, image=self.current_tk_image) # Dibujar imagen
            self.lbl_page.config(text=f"Página: {self.current_page_num + 1}/{self.pdf_document.page_count} (Zoom: {self.zoom_factor:.0%})")
        except Exception as e:
            messagebox.showerror("Error", f"Error al mostrar la página: {e}")
            traceback.print_exc()
            self.current_pil_image = None; self.current_tk_image = None; self.canvas.delete("all")
            self.lbl_page.config(text=f"Error mostrando página (Zoom: {self.zoom_factor:.0%})")

    def on_mouse_wheel(self, event):
        if not self.pdf_document or not self.current_pil_image: return
        if self.current_rect_id: # Cancelar selección si está activa al hacer zoom
            self.canvas.delete(self.current_rect_id); self.current_rect_id = None
            self.rect_start_x_canvas = None # Resetear inicio de selección
        
        scroll_direction = 0
        if event.num == 4: scroll_direction = 1
        elif event.num == 5: scroll_direction = -1
        elif hasattr(event, 'delta') and event.delta != 0: scroll_direction = 1 if event.delta > 0 else -1
        
        if scroll_direction == 0: return

        old_zoom_factor = self.zoom_factor
        if scroll_direction > 0: self.zoom_factor *= (1 + self.zoom_step)
        else: self.zoom_factor /= (1 + self.zoom_step)
        self.zoom_factor = max(self.min_zoom, min(self.max_zoom, self.zoom_factor))
        
        if abs(self.zoom_factor - old_zoom_factor) < 0.0001: # Si el cambio es insignificante
            self.zoom_factor = old_zoom_factor; return

        # Coordenadas del cursor en el canvas (antes del zoom)
        canvas_x_at_cursor_before_zoom = self.canvas.canvasx(event.x)
        canvas_y_at_cursor_before_zoom = self.canvas.canvasy(event.y)
        
        # Punto correspondiente en el documento PDF original (sin zoom)
        doc_x_at_cursor = canvas_x_at_cursor_before_zoom / old_zoom_factor
        doc_y_at_cursor = canvas_y_at_cursor_before_zoom / old_zoom_factor
        
        self.display_page() # Redibujar la página con el nuevo zoom
        if not self.current_tk_image: return

        # Nuevo tamaño de la imagen en el canvas
        img_width_after_zoom, img_height_after_zoom = self.current_tk_image.width(), self.current_tk_image.height()
        if img_width_after_zoom == 0 or img_height_after_zoom == 0: return

        # Coordenadas donde el punto del documento debería estar en la nueva imagen reescalada
        canvas_x_of_doc_point_after_zoom = doc_x_at_cursor * self.zoom_factor
        canvas_y_of_doc_point_after_zoom = doc_y_at_cursor * self.zoom_factor
        
        # Calcular el desplazamiento necesario para que el punto del documento bajo el cursor permanezca allí
        # (event.x, event.y) son las coordenadas del cursor en la ventana del canvas
        # Queremos que (canvas_x_of_doc_point_after_zoom - scroll_x_pixels) == event.x
        scroll_x_pixels = canvas_x_of_doc_point_after_zoom - event.x
        scroll_y_pixels = canvas_y_of_doc_point_after_zoom - event.y

        # Convertir a fracciones para xview_moveto/yview_moveto
        frac_x = scroll_x_pixels / img_width_after_zoom
        frac_y = scroll_y_pixels / img_height_after_zoom
        
        self.canvas.xview_moveto(max(0, min(1, frac_x)))
        self.canvas.yview_moveto(max(0, min(1, frac_y)))
            
        self.lbl_page.config(text=f"Página: {self.current_page_num + 1}/{self.pdf_document.page_count} (Zoom: {self.zoom_factor:.0%})")

    def update_page_controls(self):
        if not self.pdf_document:
            self.btn_prev.config(state=tk.DISABLED); self.btn_next.config(state=tk.DISABLED)
            self.btn_save.config(state=tk.DISABLED); self.lbl_page.config(text="Página: -/-")
            return
        self.btn_prev.config(state=tk.NORMAL if self.current_page_num > 0 else tk.DISABLED)
        self.btn_next.config(state=tk.NORMAL if self.current_page_num < self.pdf_document.page_count - 1 else tk.DISABLED)
        self.lbl_page.config(text=f"Página: {self.current_page_num + 1}/{self.pdf_document.page_count} (Zoom: {self.zoom_factor:.0%})")

    def prev_page(self):
        if self.pdf_document and self.current_page_num > 0:
            self.current_page_num -= 1; self.canvas.xview_moveto(0); self.canvas.yview_moveto(0)
            self.display_page(); self.update_page_controls()

    def next_page(self):
        if self.pdf_document and self.current_page_num < self.pdf_document.page_count - 1:
            self.current_page_num += 1; self.canvas.xview_moveto(0); self.canvas.yview_moveto(0)
            self.display_page(); self.update_page_controls()

    # --- Métodos para Selección de Rectángulo (Botón Izquierdo) ---
    def on_mouse_press(self, event):
        if not self.current_pil_image or self.is_panning: return
        if self.current_rect_id: self.canvas.delete(self.current_rect_id)

        self.rect_start_x_canvas = self.canvas.canvasx(event.x)
        self.rect_start_y_canvas = self.canvas.canvasy(event.y)
        
        self.current_rect_id = self.canvas.create_rectangle(
            self.rect_start_x_canvas, self.rect_start_y_canvas,
            self.rect_start_x_canvas, self.rect_start_y_canvas,
            outline="red", width=2
        )

    def on_mouse_drag(self, event):
        if not self.current_pil_image or self.rect_start_x_canvas is None or \
           not self.current_rect_id or self.is_panning: return
        
        cur_x_canvas = self.canvas.canvasx(event.x)
        cur_y_canvas = self.canvas.canvasy(event.y)
        
        self.canvas.coords(self.current_rect_id, 
                           self.rect_start_x_canvas, self.rect_start_y_canvas, 
                           cur_x_canvas, cur_y_canvas)

    def on_mouse_release(self, event):
        if self.is_panning: return 
        if not self.current_pil_image or self.rect_start_x_canvas is None or not self.current_rect_id:
            if self.current_rect_id: self.canvas.delete(self.current_rect_id)
            self.current_rect_id = None; self.rect_start_x_canvas = None
            return

        rect_end_x_canvas = self.canvas.canvasx(event.x)
        rect_end_y_canvas = self.canvas.canvasy(event.y)

        self.canvas.delete(self.current_rect_id)
        self.current_rect_id = None

        x0_canvas = int(min(self.rect_start_x_canvas, rect_end_x_canvas))
        y0_canvas = int(min(self.rect_start_y_canvas, rect_end_y_canvas))
        x1_canvas = int(max(self.rect_start_x_canvas, rect_end_x_canvas))
        y1_canvas = int(max(self.rect_start_y_canvas, rect_end_y_canvas))

        self.rect_start_x_canvas = None 

        if abs(x1_canvas - x0_canvas) < 5 or abs(y1_canvas - y0_canvas) < 5:
            print("Selección muy pequeña, ignorada.")
            return

        selection_box_canvas_coords = (x0_canvas, y0_canvas, x1_canvas, y1_canvas)

        # --- Bloque opcional de depuración: mostrar imagen recortada y OCR ---
        try:
            img_w, img_h = self.current_pil_image.size
            crop_x0 = max(0, selection_box_canvas_coords[0])
            crop_y0 = max(0, selection_box_canvas_coords[1])
            crop_x1 = min(img_w, selection_box_canvas_coords[2])
            crop_y1 = min(img_h, selection_box_canvas_coords[3])

            if crop_x1 > crop_x0 and crop_y1 > crop_y0:
                cropped_img_for_display = self.current_pil_image.crop((crop_x0, crop_y0, crop_x1, crop_y1))
                #self.show_cropped_image(cropped_img_for_display)

                if self.ocr_engine:
                    np_img_cropped = np.array(cropped_img_for_display)
                    debug_result = self.ocr_engine.predict(np_img_cropped) 
                    print("\n--- TEXTO DETECTADO (DEBUG DESDE ON_MOUSE_RELEASE) ---")
                    if debug_result and debug_result[0] is not None:
                        for line_info in debug_result:
                           for i in range(len(line_info['rec_texts'])):
                                text = line_info['rec_texts'][i]
                               # 1. Obtener coordenadas del recorte (relativas al PDF)
                                pdf_x0 = selection_box_canvas_coords[0] / self.zoom_factor
                                pdf_y0 = selection_box_canvas_coords[1] / self.zoom_factor
                                pdf_x1 = selection_box_canvas_coords[2] / self.zoom_factor
                                pdf_y1 = selection_box_canvas_coords[3] / self.zoom_factor

                                fitz_rect = fitz.Rect(pdf_x0, pdf_y0, pdf_x1, pdf_y1)
                                page = self.pdf_document.load_page(self.current_page_num)

                                # 2. Pintar fondo blanco en el rectángulo
                                page.draw_rect(fitz_rect, color=(1, 1, 1), fill=(1, 1, 1), overlay=True)

                                # 3. Concatenar el texto detectado por OCR (reemplaza el print)
                                ocr_text = "\n".join(line_info['rec_texts'])

                                # 4. Ajustar tamaño de fuente según el alto del rectángulo
                                rect_height_pt = fitz_rect.height
                                font_size = 18                                
                                # 5. Insertar el texto OCR en el rectángulo
                                rc = page.insert_textbox(
                                fitz_rect, ocr_text,
                                fontsize=font_size, fontname="helv",
                                color=(0, 0, 0), align=fitz.TEXT_ALIGN_LEFT,
                                rotate=0, overlay=True
                                )

                                if rc < 0:
                                    print(f"Advertencia: El texto OCR ('{ocr_text}') puede no caber completamente. Código: {rc}")

                                # 6. Volver a mostrar la página con el texto sobreescrito
                                current_xview = self.canvas.xview()
                                current_yview = self.canvas.yview()
                                self.display_page()
        except Exception as e:
            print(f"Error al procesar selección: {e}")
            traceback.print_exc()
            messagebox.showerror("Error", f"Ocurrió un error al procesar la selección: {e}")
    def show_cropped_image(self, image):
        try:
            top = tk.Toplevel(self.root)
            top.title("Imagen Recortada (Debug)")
            cropped_tk = ImageTk.PhotoImage(image)
            label = tk.Label(top, image=cropped_tk)
            label.image = cropped_tk
            label.pack()
        except Exception as e:
            print(f"Error al mostrar imagen recortada: {e}")
            traceback.print_exc()

    # --- Métodos para Panning (Botón Derecho) ---
    '''
    def on_pan_press(self, event):
        if not self.current_pil_image: return
        if self.current_rect_id: 
            self.canvas.delete(self.current_rect_id); self.current_rect_id = None
            self.rect_start_x_canvas = None
        self.is_panning = True
        self.pan_start_x_window = event.x 
        self.pan_start_y_window = event.y
        self.canvas.config(cursor="fleur")

    def on_pan_motion(self, event):
        if not self.is_panning or not self.current_pil_image: return
        dx_window = event.x - self.pan_start_x_window
        dy_window = event.y - self.pan_start_y_window
        self.canvas.xview_scroll(int(-dx_window * self.sensitivity), "units")
        self.canvas.yview_scroll(int(-dy_window * self.sensitivity), "units")
        self.pan_start_x_window = event.x 
        self.pan_start_y_window = event.y

    def on_pan_release(self, event):
        if not self.is_panning: return
        self.is_panning = False
        self.canvas.config(cursor="arrow")
    '''

        # --- Métodos para Panning (Alternativa) ---
    def on_pan_press(self, event):
        """
        Inicia el modo de paneo.
        Guarda la posición inicial del ratón y la posición actual de scroll del canvas.
        """
        if not self.current_pil_image:
            return
        
        if self.current_rect_id: 
            self.canvas.delete(self.current_rect_id)
            self.current_rect_id = None
            self.rect_start_x_canvas = None
            
        self.is_panning = True
        # Guardar coordenadas de inicio del paneo (relativas a la VENTANA del canvas)
        self.pan_start_x_window = event.x 
        self.pan_start_y_window = event.y
        
        # Guardar la posición actual de scroll del canvas (como fracción)
        # self.canvas.xview() devuelve (frac_actual_izquierda, frac_actual_derecha)
        self.initial_pan_scroll_x_frac = self.canvas.xview()[0]
        self.initial_pan_scroll_y_frac = self.canvas.yview()[0]
        
        self.canvas.config(cursor="fleur")

    def on_pan_motion(self, event):
        """
        Desplaza la vista del canvas calculando la nueva posición de scroll absoluta.
        """
        if not self.is_panning or not self.current_pil_image:
            return

        # Dimensiones totales del contenido scrolleable del canvas (la imagen renderizada)
        # Es importante que self.current_tk_image no sea None aquí.
        content_width = self.current_tk_image.width()
        content_height = self.current_tk_image.height()

        if content_width == 0 or content_height == 0: # Evitar división por cero
            return

        # Calcular el delta total del movimiento del ratón desde el inicio del paneo
        delta_mouse_x = event.x - self.pan_start_x_window
        delta_mouse_y = event.y - self.pan_start_y_window

        # Convertir el delta del movimiento del ratón a un delta de fracción de scroll.
        # Si el ratón se mueve 'delta_mouse_x' píxeles, la vista debe cambiar en
        # una fracción de 'delta_mouse_x / content_width'.
        # El signo negativo es porque si arrastras el ratón a la derecha (delta_mouse_x positivo),
        # la fracción de scroll de la izquierda (xview()[0]) debe aumentar.
        delta_scroll_frac_x = -delta_mouse_x / content_width
        delta_scroll_frac_y = -delta_mouse_y / content_height

        # Calcular la nueva fracción de scroll absoluta
        new_scroll_frac_x = self.initial_pan_scroll_x_frac + delta_scroll_frac_x
        new_scroll_frac_y = self.initial_pan_scroll_y_frac + delta_scroll_frac_y

        # Asegurarse de que la nueva fracción esté dentro de los límites [0, 1-viewport_size/content_size]
        # o simplemente [0,1] y dejar que Tkinter lo maneje (lo cual hace bastante bien).
        # Por simplicidad, se puede limitar a [0,1]
        new_scroll_frac_x = max(0.0, min(1.0, new_scroll_frac_x))
        new_scroll_frac_y = max(0.0, min(1.0, new_scroll_frac_y))
        
        # Mover la vista del canvas a la nueva posición de scroll calculada
        self.canvas.xview_moveto(new_scroll_frac_x)
        self.canvas.yview_moveto(new_scroll_frac_y)

    def on_pan_release(self, event):
        """
        Finaliza el modo de paneo.
        """
        if not self.is_panning:
            return
        self.is_panning = False
        self.canvas.config(cursor="arrow")

    def perform_ocr_and_annotate(self, image_coords_on_canvas):
        if not self.current_pil_image:
            messagebox.showwarning("Advertencia", "No hay imagen cargada para OCR.")
            return
        if not self.ocr_engine:
            messagebox.showerror("Error", "El motor OCR (PaddleOCR) no está inicializado.")
            return

        try:
            img_w, img_h = self.current_pil_image.size
            crop_x0 = max(0, image_coords_on_canvas[0])
            crop_y0 = max(0, image_coords_on_canvas[1])
            crop_x1 = min(img_w, image_coords_on_canvas[2])
            crop_y1 = min(img_h, image_coords_on_canvas[3])

            if not (crop_x1 > crop_x0 and crop_y1 > crop_y0):
                messagebox.showinfo("OCR", "Área de selección inválida para OCR.")
                return
                
            cropped_image_pil_for_ocr = self.current_pil_image.crop((crop_x0, crop_y0, crop_x1, crop_y1))
            cropped_image_np = np.array(cropped_image_pil_for_ocr)

            print(f"Realizando OCR en región (coords canvas): {image_coords_on_canvas} con lang='{self.target_lang_ocr}'")
            result = self.ocr_engine.predict(cropped_image_np)

            ocr_text_parts = []
            if result and result[0] is not None:
                for line_info in result[0]: ocr_text_parts.append(line_info[1][0])
            ocr_text = "\n".join(ocr_text_parts).strip()
            print(f"Texto OCR para anotación (PaddleOCR): '{ocr_text}'")

            if not ocr_text:
                messagebox.showinfo("OCR", "No se detectó texto en la selección con PaddleOCR para anotar.")
                return

            pdf_x0 = image_coords_on_canvas[0] / self.zoom_factor
            pdf_y0 = image_coords_on_canvas[1] / self.zoom_factor
            pdf_x1 = image_coords_on_canvas[2] / self.zoom_factor
            pdf_y1 = image_coords_on_canvas[3] / self.zoom_factor
            fitz_rect_pdf = fitz.Rect(pdf_x0, pdf_y0, pdf_x1, pdf_y1)
            
            page = self.pdf_document.load_page(self.current_page_num)
            page.draw_rect(fitz_rect_pdf, color=(1, 1, 1), fill=(1, 1, 1), overlay=True)
            rect_height_pt = fitz_rect_pdf.height
            font_size = 12
            
            rc = page.insert_textbox(fitz_rect_pdf, ocr_text,
                                     fontsize=font_size, fontname="helv",
                                     color=(0, 0, 0), align=fitz.TEXT_ALIGN_LEFT,
                                     rotate=0, overlay=True)
            if rc < 0: print(f"Advertencia: Texto OCR ('{ocr_text}') puede no caber. Código PyMuPDF: {rc}")

            current_xview_frac = self.canvas.xview()[0]
            current_yview_frac = self.canvas.yview()[0]
            self.display_page()
            self.canvas.xview_moveto(current_xview_frac)
            self.canvas.yview_moveto(current_yview_frac)

        except Exception as e:
            messagebox.showerror("Error de OCR/Anotación", f"Ocurrió un error: {e}\nTipo: {type(e)}")
            traceback.print_exc()
            try: # Intento de restauración de vista en caso de error
                current_xview_frac = self.canvas.xview()[0]
                current_yview_frac = self.canvas.yview()[0]
                self.display_page()
                self.canvas.xview_moveto(current_xview_frac)
                self.canvas.yview_moveto(current_yview_frac)
            except Exception as e_restore:
                print(f"Error adicional al restaurar vista: {e_restore}")

    def save_pdf(self):
        if not self.pdf_document:
            messagebox.showwarning("Advertencia", "No hay PDF cargado para guardar.")
            return
        filepath = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=(("Archivos PDF", "*.pdf"), ("Todos los archivos", "*.*")),
            title="Guardar PDF modificado como..."
        )
        if not filepath: return
        try:
            self.pdf_document.save(filepath, garbage=4, deflate=True, clean=True)
            messagebox.showinfo("Guardado", f"PDF modificado guardado en:\n{filepath}")
        except Exception as e:
            messagebox.showerror("Error al Guardar", f"No se pudo guardar el PDF: {e}")
            traceback.print_exc()

# --- INICIO DE LA APLICACIÓN ---
if __name__ == "__main__":
    print("Iniciando aplicación PDF OCR Annotator con PaddleOCR...")
    # Para obtener los valores de config y mostrarlos sin ejecutar toda la app
    _dummy_root = tk.Tk()
    _dummy_root.withdraw() # Ocultar la ventana dummy
    _dummy_app_for_config = PDFOCRAnnotator(_dummy_root)
    target_lang = _dummy_app_for_config.target_lang_ocr
    ocr_version = _dummy_app_for_config.ocr_model_version
    _dummy_root.destroy() 

    print(f"Intentando usar idioma: '{target_lang}', versión OCR: '{ocr_version}'.")
    print("La primera vez, PaddleOCR descargará modelos (requiere internet).")
    print("Si la inicialización de PaddleOCR falla, revisa la consola.")

    root = tk.Tk()
    app = PDFOCRAnnotator(root)
    if app.ocr_engine is None:
        print("ADVERTENCIA: El motor OCR no se inicializó. La funcionalidad OCR no estará disponible.")
    root.mainloop()