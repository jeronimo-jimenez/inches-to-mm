# App para convertir pulgadas a milímetros en planos
# Modo de funcionamiento:
# 1. Ejecutar el script
# 2. Abrir un pdf con el plano
# 3. Hacer un rectángulo alrededor de la zona a convertir

# Jerónimo Manuel Jiménez Mateos

# ========================================================
# =======================Librerías========================
# ========================================================
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import fitz  # PyMuPDF
import os
import time
import numpy as np
from paddleocr import PaddleOCR

# ========================================================
# ====================Clase principal=====================
# ========================================================
class InchesToMMConverter:
    def __init__(self, root):
        self.root = root
        self.root.title("Inches to MM Converter")
        self.root.geometry("1920x1080")

        self.pdf_document = None
        self.current_page = 0
        self.current_pil_image = None # Imagen renderizada
        self.current_tk_image = None

        # Coordenadas del rectángulo
        self.rect_start_x = None
        self.rect_start_y = None
        self.rect_end_x = None
        self.rect_end_y = None
        self.current_rect_id = None

        # Atributos del zoom
        self.min_area = 10 
        self.zoom_factor = 1.0
        self.zoom_step = 0.1
        self.min_zoom = 0.2
        self.max_zoom = 5.0

        # Atributos del panning
        self.pan_start_x = 0
        self.pan_start_y = 0
        self.inital_pan_scroll_xfrac = 0.0
        self.inital_pan_scroll_yfrac = 0.0
        self.is_panning = False

        # Pila de deshacer
        self.undo_stack = []  # [(page_number, fitz.Rect, text, rotation)]

        # PaddleOCR
        self.ocr_engine = None
        self.target_language = 'en'
        self.ocr_model_version = 'PP-OCRv5'
        self.text_recognition_ = 'PP-OCRv5_mobile_rec'
        self.initialize_ocr()

        # Frames
        controls_frame = tk.Frame(root)
        controls_frame.pack(pady = 10)

        self.canvas_frame = tk.Frame(root)
        self.canvas_frame.pack(fill=tk.BOTH, expand=True)

        # Controles
        self.btn_open = tk.Button(controls_frame, text="Abrir PDF", command=self.open_pdf)
        self.btn_open.pack(side=tk.LEFT, padx=5)

        self.btn_prev = tk.Button(controls_frame, text="Página Anterior", command=self.prev_page, state = tk.DISABLED)
        self.btn_prev.pack(side=tk.LEFT, padx=5)

        self.lbl_page = tk.Label(controls_frame, text="Página: -/-")
        self.lbl_page.pack(side=tk.LEFT, padx=5)

        self.btn_next = tk.Button(controls_frame, text="Página Siguiente", command=self.next_page, state = tk.DISABLED)
        self.btn_next.pack(side=tk.LEFT, padx=5)

        self.btn_save = tk.Button(controls_frame, text="Guardar PDF", command=self.save_pdf, state = tk.DISABLED)
        self.btn_save.pack(side=tk.LEFT, padx=5)

        # Canvas para mostrar el PDF
        self.canvas = tk.Canvas(self.canvas_frame, bg="lightgrey", cursor="arrow")
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        # Bindings para eventos del ratón
        self.canvas.bind("<ButtonPress-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)
        
        self.canvas.bind("<ButtonPress-3>", self.on_pan_press)
        self.canvas.bind("<B3-Motion>", self.on_pan_motion)
        self.canvas.bind("<ButtonRelease-3>", self.on_pan_release)
        
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel)

        self.root.bind_all("<Control-z>", self.undo_last_action)


    def initialize_ocr(self):
        """Inicializa el motor OCR de PaddleOCR."""
        if self.ocr_engine is None:
            self.ocr_engine = PaddleOCR(
                use_angle_cls=False,                             # Habilita la clasificación de ángulos
                lang=self.target_language,
                ocr_version = self.ocr_model_version,
                text_recognition_model_name = self.text_recognition_
            )
        else:
            self.ocr_engine.lang = self.target_language
            self.ocr_engine.ocr_version = self.ocr_model_version

    def open_pdf(self):
        """Abre un archivo PDF y carga la primera página."""
        file_path = filedialog.askopenfilename(
            title = "Seleccionar archivo PDF",
            filetypes=(("Archivos PDF", "*.pdf"), ("Todos los archivos", "*.*"))
        )
        if not file_path:
            return

        self.pdf_document = fitz.open(file_path)
        self.current_page = 0
        self.zoom_factor = 1.0
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)
        self.render_page()
        self.update_page_controls()
    
    def update_page_controls(self):
        """Actualiza los controles de navegación de páginas."""
        if self.pdf_document:
            self.lbl_page.config(text=f"Página: {self.current_page + 1}/{len(self.pdf_document)}")
            self.btn_prev.config(state=tk.NORMAL if self.current_page > 0 else tk.DISABLED)
            self.btn_next.config(state=tk.NORMAL if self.current_page < len(self.pdf_document) - 1 else tk.DISABLED)
            self.btn_save.config(state=tk.NORMAL)
        else:
            self.lbl_page.config(text="Página: -/-")
            self.btn_prev.config(state=tk.DISABLED)
            self.btn_next.config(state=tk.DISABLED)
            self.btn_save.config(state=tk.DISABLED)

    def render_page(self):
        if not self.pdf_document or not (0 <= self.current_page < len(self.pdf_document)):
            # Si no hay documento o la página es inválida, limpiar el canvas
            self.canvas.delete("all")
            self.current_pil_image = None
            self.current_tk_image = None

            zoom_text = f"(Zoom: {self.zoom_factor:.0%})" if self.pdf_document else ""
            self.lbl_page.config(text=f"Página: -/- {zoom_text}")
            return
        # Renderizar la página actual
        page = self.pdf_document[self.current_page]
        mat = fitz.Matrix(self.zoom_factor, self.zoom_factor)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        self.current_pil_image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        self.current_tk_image = ImageTk.PhotoImage(self.current_pil_image)
        self.canvas.delete("all")

        # Scroll Region
        self.canvas.config(scrollregion=(0, 0, self.current_tk_image.width(), self.current_tk_image.height()))
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.current_tk_image)
        self.lbl_page.config(text=f"Página: {self.current_page + 1}/{len(self.pdf_document)} (Zoom: {self.zoom_factor:.0%})")

    def prev_page(self):
        """Cambia a la página anterior."""
        if self.pdf_document and self.current_page > 0:
            self.current_page -= 1
            self.canvas.xview_moveto(0)
            self.canvas.yview_moveto(0)
            self.render_page()
            self.update_page_controls()
    
    def next_page(self):
        """Cambia a la página siguiente."""
        if self.pdf_document and self.current_page < len(self.pdf_document) - 1:
            self.current_page += 1
            self.canvas.xview_moveto(0)
            self.canvas.yview_moveto(0)
            self.render_page()
            self.update_page_controls()
    
    def save_pdf(self):
        """Guarda el PDF con las modificaciones."""
        if not self.pdf_document:
            messagebox.showerror("Error", "No hay documento PDF abierto.")
            return

        save_path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("Archivos PDF", "*.pdf"), ("Todos los archivos", "*.*")],
            title="Guardar PDF modificado como..."
        )
        if not save_path:
            return

        self.pdf_document.save(save_path, garbage=4, deflate=True, clean=True)
        messagebox.showinfo("Éxito", "PDF guardado correctamente.")

    def convert_inches_to_mm(self, text):
        """Convierte medidas en pulgadas a milímetros."""
        import re
        
        # Limpiar el texto eliminando caracteres no deseados excepto números, puntos y espacios
        cleaned_text = re.sub(r'[^\d\.\s]', '', text.strip())
        print(f"Texto original: '{text}'")
        print(f"Texto limpio antes de correcciones: '{cleaned_text}'")
        # Corregir números que empiezan por punto añadiendo un 0 antes del punto
        cleaned_text = re.sub(r'(^|\s)\.(\d+)', r'\g<1>0.\2', cleaned_text)        
        print(f"Texto limpio: '{cleaned_text}'")
        # Extraer números del texto
        numbers = re.findall(r'\d+\.?\d*', cleaned_text)

        if not numbers:
            # Si no se encuentra ningún número, devolver el texto original
            print(f"No se encontraron números en: '{text}' -> devolviendo texto original")
            return text
        
        converted_numbers = []
        for num_str in numbers:
            try:
                # Convertir a float
                inches = float(num_str)
                # Convertir pulgadas a milímetros (1 pulgada = 25.4 mm)
                mm = inches * 25.4
                # Mantener 4 decimales
                mm_formatted = f"{mm:.4f}"
                # Eliminar ceros innecesarios al final
                converted_numbers.append(mm_formatted)
                print(f"Conversión: {inches}\" = {mm_formatted} mm")
            except ValueError:
                # Si no se puede convertir, mantener el valor original
                print(f"Error al convertir '{num_str}' -> manteniendo valor original")
                converted_numbers.append(num_str)
        
        # Si solo hay un número, devolver solo ese número convertido
        if len(converted_numbers) == 1:
            return converted_numbers[0]
        else:
            # Si hay múltiples números, devolverlos separados por espacios
            return ' '.join(converted_numbers)
    def process_selection(self):
        """Procesa la selección del rectángulo y convierte las unidades - VERSIÓN OPTIMIZADA."""
        # Validación temprana combinada
        if not all([self.current_pil_image, self.rect_start_x is not None, 
                    self.current_rect_id, self.selection_coords]):
            messagebox.showwarning("Advertencia", 
                                "No hay selección válida o coordenadas de selección.")
            return

        # Pre-calcular valores reutilizables
        x0_canvas, y0_canvas, x1_canvas, y1_canvas = self.selection_coords
        img_width, img_height = self.current_pil_image.size
        zoom_inv = 1.0 / self.zoom_factor  # Evitar divisiones repetidas
        
        # Calcular región de recorte una sola vez
        padding = 10
        crop_coords = (
            max(0, x0_canvas - padding),
            max(0, y0_canvas - padding), 
            min(img_width, x1_canvas + padding),
            min(img_height, y1_canvas + padding)
        )
        crop_x0, crop_y0, crop_x1, crop_y1 = crop_coords
        
        # Validar dimensiones del recorte
        if crop_x1 <= crop_x0 or crop_y1 <= crop_y0:
            messagebox.showwarning("Advertencia", "Área de selección inválida.")
            return
        
        # OCR optimizado
        cropped_image = self.current_pil_image.crop(crop_coords)
        
        if self.ocr_engine is None:
            messagebox.showerror("Error", "Motor OCR no disponible.")
            return
                   
        # Convertir a numpy array una sola vez
        cropped_array = np.array(cropped_image)
        start = time.time()
        ocr_results = self.ocr_engine.predict(cropped_array)
        end = time.time()
        print(f"Tiempo de OCR: {end - start:.2f} segundos")
        
        if not ocr_results:
            messagebox.showwarning("Advertencia", "No se detectó texto en la selección.")
            return
        
        # Procesar primer resultado válido solamente
        result = ocr_results[0]
        if not result.get('rec_texts'):
            messagebox.showwarning("Advertencia", "No se pudo extraer texto.")
            return
        
        # Combinar texto una sola vez
        text = "\n".join(result['rec_texts'])
        if not text.strip():
            messagebox.showwarning("Advertencia", "Texto extraído está vacío.")
            return
        
        # Pre-calcular rectángulos
        pdf_coords = (
            x0_canvas * zoom_inv,
            y0_canvas * zoom_inv,
            x1_canvas * zoom_inv, 
            y1_canvas * zoom_inv
        )
        
        rect = fitz.Rect(*pdf_coords)
        rect2 = fitz.Rect(
            crop_x0 * zoom_inv,
            crop_y0 * zoom_inv,
            crop_x1 * zoom_inv,
            crop_y1 * zoom_inv
        )
        
        # Determinar orientación basada en aspecto
        rotate_angle = 90 if rect2.height > rect2.width else 0
        
        # Cargar página una sola vez
        page = self.pdf_document.load_page(self.current_page)
        
        # Procesar conversión de texto
        converted_text = self.convert_inches_to_mm(text)
        print(f"Texto original: {text}")
        print(f"Texto convertido ({type(converted_text)}): {converted_text}")
        
        # Optimización: Solo crear pixmap de alta resolución si es necesario
        # Usar matriz 1.5x en lugar de 2x para reducir memoria
        original_page_pixmap = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
        original_page_data = original_page_pixmap.tobytes("png")
        
        # Limpiar pixmap de memoria inmediatamente
        original_page_pixmap = None
        
        # Aplicar modificaciones al PDF
        page.draw_rect(rect, color=(1, 1, 1), fill=(1, 1, 1), overlay=True)
        
        # Inserción de texto optimizada con rangos más eficientes
        font_sizes = range(18, 5, -3)  # Pasos más grandes: 18, 15, 12, 9, 6
        text_inserted = False
        
        for font_size in font_sizes:
            rc = page.insert_textbox(
                rect2, converted_text, 
                fontsize=font_size, 
                fontname="helv",
                color=(0, 0, 0), 
                align=fitz.TEXT_ALIGN_CENTER,
                rotate=rotate_angle, 
                overlay=True
            )
            if rc >= 0:
                text_inserted = True
                break
        
        if not text_inserted:
            # Intentar una última vez con el tamaño mínimo exacto
            rc = page.insert_textbox(
                rect2, converted_text,
                fontsize=6,
                fontname="helv", 
                color=(0, 0, 0),
                align=fitz.TEXT_ALIGN_CENTER,
                rotate=rotate_angle,
                overlay=True
            )
            if rc < 0:
                messagebox.showerror("Error", 
                                "No se pudo insertar el texto en el PDF, incluso con tamaño mínimo.")
                return
            font_size = 6
        
        # Guardar estado para undo de manera eficiente
        undo_data = {
            "page_number": self.current_page,
            "rect": rect,              
            "rect2": rect2,            
            "text": converted_text,
            "fontsize": font_size,
            "rotation": rotate_angle,
            "original_page_data": original_page_data,
            "restore_method": "full_page"
        }
        self.undo_stack.append(undo_data)
        
        # Preservar vista y renderizar
        view_state = (self.canvas.xview(), self.canvas.yview())
        self.render_page()
        self.canvas.xview_moveto(view_state[0][0])
        self.canvas.yview_moveto(view_state[1][0])

    def undo_last_action(self, event=None):
        """Deshace la última acción restaurando el estado original de la página."""
        if not self.undo_stack:
            messagebox.showinfo("Deshacer", "No hay acciones para deshacer.")
            return

        last_action = self.undo_stack.pop()
        
        try:
            # Método 1: Restauración completa de página (recomendado)
            if last_action.get("restore_method") == "full_page" and "original_page_data" in last_action:
                # Reemplazar completamente la página con la versión original
                page = self.pdf_document.load_page(last_action["page_number"])
                
                # Crear una nueva página limpia
                page_rect = page.rect
                
                # Limpiar completamente la página actual
                page.clean_contents()
                
                # Restaurar la imagen original de la página completa
                original_pixmap = fitz.Pixmap(last_action["original_page_data"])
                page.insert_image(page_rect, pixmap=original_pixmap)
                
            else:
                # Método fallback: usar método de cubierta (menos efectivo)
                page = self.pdf_document.load_page(last_action["page_number"])
                
                # Intentar eliminar elementos específicos primero
                try:
                    # Limpiar contenidos de dibujo temporal
                    page.clean_contents()
                except:
                    pass
                
                # Cubrir áreas como último recurso
                union_rect = fitz.Rect(
                    min(last_action["rect"].x0, last_action["rect2"].x0) - 5,
                    min(last_action["rect"].y0, last_action["rect2"].y0) - 5,
                    max(last_action["rect"].x1, last_action["rect2"].x1) + 5,
                    max(last_action["rect"].y1, last_action["rect2"].y1) + 5
                )
                page.draw_rect(union_rect, color=(1, 1, 1), fill=(1, 1, 1), overlay=True)

        except Exception as e:
            print(f"Error en undo: {e}")
            messagebox.showerror("Error", f"No se pudo deshacer la acción: {str(e)}")
            return

        # Redibujar página
        xview, yview = self.canvas.xview(), self.canvas.yview()
        self.render_page()
        self.canvas.xview_moveto(xview[0])
        self.canvas.yview_moveto(yview[0])


    # Método alternativo más avanzado (usar solo si el anterior no funciona)
    def undo_last_action_advanced(self, event=None):
        """Método alternativo que reconstruye la página desde cero."""
        if not self.undo_stack:
            messagebox.showinfo("Deshacer", "No hay acciones para deshacer.")
            return

        last_action = self.undo_stack.pop()
        
        try:
            page_num = last_action["page_number"]
            
            # Crear una nueva página temporal
            temp_doc = fitz.open()
            temp_page = temp_doc.new_page(width=self.pdf_document[page_num].rect.width, 
                                        height=self.pdf_document[page_num].rect.height)
            
            # Restaurar la imagen original en la página temporal
            if "original_page_data" in last_action:
                original_pixmap = fitz.Pixmap(last_action["original_page_data"])
                temp_page.insert_image(temp_page.rect, pixmap=original_pixmap)
            
            # Reemplazar la página actual con la temporal
            self.pdf_document.delete_page(page_num)
            self.pdf_document.insert_page(page_num, temp_page)
            
            temp_doc.close()
            
        except Exception as e:
            print(f"Error en undo avanzado: {e}")
            messagebox.showerror("Error", f"No se pudo deshacer la acción: {str(e)}")
            return

        # Redibujar página
        xview, yview = self.canvas.xview(), self.canvas.yview()
        self.render_page()
        self.canvas.xview_moveto(xview[0])
        self.canvas.yview_moveto(yview[0])

        messagebox.showinfo("Deshacer", "Acción deshecha correctamente.")

    # ========================================================
    # ==================Eventos del ratón=====================
    # ========================================================
    def on_mouse_down(self, event):
        """Inicia el rectángulo de selección."""
        if self.current_rect_id is not None:
            self.canvas.delete(self.current_rect_id)

        self.rect_start_x = self.canvas.canvasx(event.x)
        self.rect_start_y = self.canvas.canvasy(event.y)

        self.current_rect_id = self.canvas.create_rectangle(
            self.rect_start_x, self.rect_start_y, 
            self.rect_start_x, self.rect_start_y,
            outline="red", width=2, tags="rect"
        )
    
    def on_mouse_drag(self, event):
        """Actualiza el rectángulo de selección mientras se arrastra."""
        if not self.current_pil_image or self.rect_start_x is None or \
        not self.current_rect_id or self.is_panning: return

        # Actualiza las coordenadas del rectángulo
        cur_x_canvas = self.canvas.canvasx(event.x)
        cur_y_canvas = self.canvas.canvasy(event.y)

        self.canvas.coords( self.current_rect_id,
                            self.rect_start_x, self.rect_start_y,
                            cur_x_canvas, cur_y_canvas)
        
    def on_mouse_up(self, event):
        """Finaliza el rectángulo de selección y procesa la conversión."""
        if self.is_panning:
            return
        if not self.current_pil_image or self.rect_start_x is None or \
            not self.current_rect_id:
            if self.current_rect_id is not None:
                self.canvas.delete(self.current_rect_id)
                self.rect_start_x = None
                self.rect_start_y = None
            return
        
        self.rect_end_x = self.canvas.canvasx(event.x)
        self.rect_end_y = self.canvas.canvasy(event.y)

        x0_canvas = int(min(self.rect_start_x, self.rect_end_x))
        y0_canvas = int(min(self.rect_start_y, self.rect_end_y))
        x1_canvas = int(max(self.rect_start_x, self.rect_end_x))
        y1_canvas = int(max(self.rect_start_y, self.rect_end_y))

        self.selection_coords = (x0_canvas, y0_canvas, x1_canvas, y1_canvas)

        if(abs(x1_canvas - x0_canvas) < self.min_area or 
            abs(y1_canvas - y0_canvas) < self.min_area):
            messagebox.showwarning("Advertencia", "El área seleccionada es demasiado pequeña.")
            return
        
        # Procesar la selección
        self.process_selection()

        # Elimina el rectángulo de selección
        self.canvas.delete(self.current_rect_id)
        self.current_rect_id = None
        self.rect_start_x = self.rect_start_y = self.rect_end_x = self.rect_end_y = None


    def on_pan_press(self, event):
        """Inicia el panning."""
        self.is_panning = True

        self.pan_start_x = event.x
        self.pan_start_y = event.y
         
        # Guardar la posición inicial del canvas
        self.inital_pan_scroll_xfrac = self.canvas.xview()[0]
        self.inital_pan_scroll_yfrac = self.canvas.yview()[0]

        self.canvas.config(cursor="fleur")
    
    def on_pan_motion(self, event):
        """Mueve el canvas durante el panning."""
        if not self.is_panning:
            return
        
        content_width = self.current_tk_image.width()
        content_height = self.current_tk_image.height()

        if content_width == 0 or content_height == 0:
            return
        
        # Calcular el desplazamiento basado en la posición del ratón
        dx = event.x - self.pan_start_x
        dy = event.y - self.pan_start_y

        delta_scroll_xfrac = -dx / content_width
        delta_scroll_yfrac = -dy / content_height

        new_xfrac = self.inital_pan_scroll_xfrac + delta_scroll_xfrac
        new_yfrac = self.inital_pan_scroll_yfrac + delta_scroll_yfrac
        # Asegurarse de que el nuevo desplazamiento esté dentro de los límites
        new_xfrac = max(0, min(1, new_xfrac))
        new_yfrac = max(0, min(1, new_yfrac))

        # Mover el canvas
        self.canvas.xview_moveto(new_xfrac)
        self.canvas.yview_moveto(new_yfrac)

    def on_pan_release(self, event):
        """Finaliza el panning."""
        if not self.is_panning:
            return
        self.is_panning = False
        self.canvas.config(cursor="arrow")

    def on_mouse_wheel(self, event):
        """Maneja el zoom con la rueda del ratón."""
        if not self.pdf_document:
            return

        if self.current_rect_id is not None:
            self.canvas.delete(self.current_rect_id)
            self.current_rect_id = None
            self.rect_start_x = None
            self.rect_start_y = None
        
        scroll_direction = "up" if event.delta > 0 else "down" if event.delta < 0 else "none"
        
        if scroll_direction == "none":
            return
        
        # Evitar el zoom si se está haciendo panning
        if self.is_panning:
            return
        
        old_zoom_factor = self.zoom_factor
        if scroll_direction == "up":
            # Aumentar el zoom
            self.zoom_factor *= 1 + self.zoom_step
        elif scroll_direction == "down":
            # Disminuir el zoom
            self.zoom_factor /= 1 + self.zoom_step
        # Asegurarse de que el zoom esté dentro de los límites
        self.zoom_factor = max(self.min_zoom, min(self.max_zoom, self.zoom_factor))

        if abs(self.zoom_factor - old_zoom_factor) < 0.01:
            # Si el zoom no ha cambiado significativamente, no hacer nada
            return 
        
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        canvas_cx = self.canvas.canvasx(canvas_width / 2)
        canvas_cy = self.canvas.canvasy(canvas_height / 2)

        # Punto correspondiente en la imagen
        img_cx = canvas_cx / old_zoom_factor
        img_cy = canvas_cy / old_zoom_factor

        # Renderizar la página con el nuevo zoom
        self.render_page()

        # Nuevo tamaño de la imagen
        new_img_width, new_img_height = self.current_tk_image.width(), self.current_tk_image.height()

        # Calcular las nuevas coordenadas del cursor en la imagen
        new_canvas_cx = img_cx * self.zoom_factor
        new_canvas_cy = img_cy * self.zoom_factor

        # Punto de referencia para el scroll
        scroll_xfrac = (new_canvas_cx - canvas_width / 2) / new_img_width
        scroll_yfrac = (new_canvas_cy - canvas_height / 2) / new_img_height

        # Asegurarse de que el scroll esté dentro de los límites
        scroll_xfrac = max(0, min(1, scroll_xfrac))
        scroll_yfrac = max(0, min(1, scroll_yfrac))

        # Mover el canvas al nuevo scroll
        self.canvas.xview_moveto(scroll_xfrac)
        self.canvas.yview_moveto(scroll_yfrac)

if __name__ == "__main__":
    print("Iniciando aplicación PDF OCR Annotator con PaddleOCR...")
    # Para obtener los valores de config y mostrarlos sin ejecutar toda la app
    _dummy_root = tk.Tk()
    _dummy_root.withdraw() # Ocultar la ventana dummy
    _dummy_app_for_config = InchesToMMConverter(_dummy_root)
    target_lang = _dummy_app_for_config.target_language
    ocr_version = _dummy_app_for_config.ocr_model_version
    _dummy_root.destroy() 

    print(f"Intentando usar idioma: '{target_lang}', versión OCR: '{ocr_version}'.")
    print("La primera vez, PaddleOCR descargará modelos (requiere internet).")
    print("Si la inicialización de PaddleOCR falla, revisa la consola.")

    root = tk.Tk()
    app = InchesToMMConverter(root)
    if app.ocr_engine is None:
        print("ADVERTENCIA: El motor OCR no se inicializó. La funcionalidad OCR no estará disponible.")
    root.mainloop()