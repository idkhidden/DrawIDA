from PyQt5 import QtWidgets, QtGui, QtCore
import ida_kernwin
import idaapi

class TextItem:
    def __init__(self, text, pos, color, font_size=14):
        self.text = text
        self.pos = QtCore.QPoint(pos)
        self.color = QtGui.QColor(color)
        self.font_size = font_size

class Stroke:
    def __init__(self, points, color, width):
        self.points = [QtCore.QPoint(pt) for pt in points]
        self.color = QtGui.QColor(color)
        self.width = width

class WhiteboardCanvas(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.pen_color = QtGui.QColor("black")
        self.pen_size = 2
        self.text_font_size = 14
        self.strokes = []
        self.text_items = []
        self.undo_stack = []
        self.redo_stack = []

        self.last_point = None
        self.current_stroke = None
        self.drawing = False

        self.mode = "draw"
        self.pending_text = None

        self.selecting = False
        self.selection_rect = QtCore.QRect()
        self.selected_strokes = []
        self.selected_texts = []
        self.drag_offset = QtCore.QPoint()
        self.dragging_selection = False

        self.cursor_pos = None
        self.setMouseTracking(True)
        self.setMinimumSize(400, 300)

    def text_rect(self, text):
        font = QtGui.QFont("Arial", text.font_size)
        metrics = QtGui.QFontMetrics(font)
        rect = metrics.boundingRect(text.text)
        rect.moveTopLeft(text.pos)
        rect.moveTop(rect.top() - metrics.ascent())
        return rect

    def point_near_stroke(self, point, stroke, threshold=5):
        for pt in stroke.points:
            if (pt - point).manhattanLength() <= threshold + stroke.width:
                return True
        return False

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update()

    def mousePressEvent(self, event):
        if event.button() != QtCore.Qt.LeftButton:
            return
        
        self.cursor_pos = event.pos()

        if self.mode == "text" and self.pending_text:
            self.push_undo()
            self.text_items.append(TextItem(self.pending_text, event.pos(), self.pen_color, self.text_font_size))
            self.pending_text = None
            self.update()
            return

        elif self.mode == "select":
            hit = False
            for text in self.selected_texts:
                if self.text_rect(text).contains(event.pos()):
                    self.dragging_selection = True
                    self.drag_offset = event.pos()
                    hit = True
                    break
            
            if not hit:
                for stroke in self.selected_strokes:
                    if self.point_near_stroke(event.pos(), stroke):
                        self.dragging_selection = True
                        self.drag_offset = event.pos()
                        hit = True
                        break
            
            if not hit:
                self.selecting = True
                self.selection_rect.setTopLeft(event.pos())
                self.selection_rect.setBottomRight(event.pos())
                self.selected_strokes.clear()
                self.selected_texts.clear()
            self.update()

        elif self.mode == "draw":
            self.push_undo()
            self.last_point = event.pos()
            self.current_stroke = Stroke([self.last_point], self.pen_color, self.pen_size)
            self.strokes.append(self.current_stroke)
            self.drawing = True

        elif self.mode == "erase":
            self.push_undo()
            self.erase_at(event.pos())
            self.drawing = True

    def mouseMoveEvent(self, event):
        self.cursor_pos = event.pos()
        
        if self.mode == "select":
            if self.dragging_selection:
                delta = event.pos() - self.drag_offset
                for stroke in self.selected_strokes:
                    stroke.points = [pt + delta for pt in stroke.points]
                for text in self.selected_texts:
                    text.pos += delta
                self.drag_offset = event.pos()
            elif self.selecting:
                self.selection_rect.setBottomRight(event.pos())
                
        elif self.mode == "draw" and self.drawing and self.current_stroke:
            if not self.last_point or (event.pos() - self.last_point).manhattanLength() > 1:
                self.current_stroke.points.append(event.pos())
                self.last_point = event.pos()
                
        elif self.mode == "erase" and self.drawing:
            self.erase_at(event.pos())
            
        self.update()

    def mouseReleaseEvent(self, event):
        self.cursor_pos = event.pos()
        
        if self.mode == "select":
            if self.selecting:
                self.selecting = False
                self.selected_strokes.clear()
                self.selected_texts.clear()
                
                normalized_rect = self.selection_rect.normalized()
                for stroke in self.strokes:
                    for pt in stroke.points:
                        if normalized_rect.contains(pt):
                            if stroke not in self.selected_strokes:
                                self.selected_strokes.append(stroke)
                            break
                
                for text in self.text_items:
                    if normalized_rect.intersects(self.text_rect(text)):
                        self.selected_texts.append(text)
                        
                self.selection_rect = QtCore.QRect()
            self.dragging_selection = False
            
        elif self.mode in ["draw", "erase"]:
            self.drawing = False
            self.current_stroke = None
            
        self.update()

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_Delete:
            if self.selected_strokes or self.selected_texts:
                self.delete_selection()
        elif event.key() == QtCore.Qt.Key_Escape:
            self.selected_strokes.clear()
            self.selected_texts.clear()
            self.pending_text = None
            self.update()

    def erase_at(self, pos):
        radius = self.pen_size + 3
        
        for stroke in self.strokes[:]:
            if self.point_near_stroke(pos, stroke, radius):
                self.strokes.remove(stroke)
        
        for text in self.text_items[:]:
            if self.text_rect(text).contains(pos):
                self.text_items.remove(text)

    def delete_selection(self):
        if not self.selected_strokes and not self.selected_texts:
            return
            
        self.push_undo()
        
        for stroke in self.selected_strokes:
            if stroke in self.strokes:
                self.strokes.remove(stroke)
        
        for text in self.selected_texts:
            if text in self.text_items:
                self.text_items.remove(text)
        
        self.selected_strokes.clear()
        self.selected_texts.clear()
        self.update()

    def get_selection_bounds(self):
        if not self.selected_strokes and not self.selected_texts:
            return None
            
        min_x = min_y = max_x = max_y = None
        
        for stroke in self.selected_strokes:
            for pt in stroke.points:
                x, y = pt.x(), pt.y()
                if min_x is None:
                    min_x = max_x = x
                    min_y = max_y = y
                else:
                    min_x = min(min_x, x)
                    min_y = min(min_y, y)
                    max_x = max(max_x, x)
                    max_y = max(max_y, y)
        
        for text in self.selected_texts:
            rect = self.text_rect(text)
            x1, y1 = rect.topLeft().x(), rect.topLeft().y()
            x2, y2 = rect.bottomRight().x(), rect.bottomRight().y()
            if min_x is None:
                min_x, min_y, max_x, max_y = x1, y1, x2, y2
            else:
                min_x = min(min_x, x1)
                min_y = min(min_y, y1)
                max_x = max(max_x, x2)
                max_y = max(max_y, y2)
        
        if min_x is not None:
            return QtCore.QRect(QtCore.QPoint(min_x, min_y), QtCore.QPoint(max_x, max_y))
        return None

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.fillRect(self.rect(), QtGui.QColor("white"))

        for stroke in self.strokes:
            pen = QtGui.QPen(stroke.color, stroke.width, QtCore.Qt.SolidLine,
                           QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin)
            painter.setPen(pen)
            if len(stroke.points) > 1:
                for i in range(1, len(stroke.points)):
                    painter.drawLine(stroke.points[i-1], stroke.points[i])
            elif len(stroke.points) == 1:
                painter.drawPoint(stroke.points[0])

        for text in self.text_items:
            painter.setPen(QtGui.QPen(text.color))
            painter.setFont(QtGui.QFont("Arial", text.font_size))
            painter.drawText(text.pos, text.text)

        if self.selecting:
            pen = QtGui.QPen(QtGui.QColor(0, 120, 215), 1, QtCore.Qt.DashLine)
            brush = QtGui.QBrush(QtGui.QColor(0, 120, 215, 50))
            painter.setPen(pen)
            painter.setBrush(brush)
            painter.drawRect(self.selection_rect.normalized())

        if self.selected_strokes or self.selected_texts:
            bounds = self.get_selection_bounds()
            if bounds:
                pen = QtGui.QPen(QtGui.QColor(0, 120, 215), 2, QtCore.Qt.DashLine)
                painter.setPen(pen)
                painter.setBrush(QtCore.Qt.NoBrush)
                painter.drawRect(bounds.normalized())

        if self.cursor_pos and self.mode in ["draw", "erase"]:
            painter.setPen(QtCore.Qt.NoPen)
            if self.mode == "draw":
                painter.setBrush(QtGui.QBrush(self.pen_color))
            else:
                painter.setBrush(QtGui.QBrush(QtGui.QColor(255, 0, 0, 128)))
            radius = max(2, self.pen_size // 2)
            painter.drawEllipse(self.cursor_pos, radius, radius)

    def push_undo(self):
        strokes_copy = [Stroke(list(s.points), s.color, s.width) for s in self.strokes]
        text_copy = [TextItem(t.text, QtCore.QPoint(t.pos), t.color, t.font_size) for t in self.text_items]
        self.undo_stack.append((strokes_copy, text_copy))
        if len(self.undo_stack) > 50:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def undo(self):
        if self.undo_stack:
            current_strokes = [Stroke(list(s.points), s.color, s.width) for s in self.strokes]
            current_texts = [TextItem(t.text, QtCore.QPoint(t.pos), t.color, t.font_size) for t in self.text_items]
            self.redo_stack.append((current_strokes, current_texts))
            
            self.strokes, self.text_items = self.undo_stack.pop()
            self.selected_strokes.clear()
            self.selected_texts.clear()
            self.update()

    def redo(self):
        if self.redo_stack:
            current_strokes = [Stroke(list(s.points), s.color, s.width) for s in self.strokes]
            current_texts = [TextItem(t.text, QtCore.QPoint(t.pos), t.color, t.font_size) for t in self.text_items]
            self.undo_stack.append((current_strokes, current_texts))
            
            self.strokes, self.text_items = self.redo_stack.pop()
            self.selected_strokes.clear()
            self.selected_texts.clear()
            self.update()

    def set_draw_mode(self):
        self.mode = "draw"
        self.pending_text = None
        self.update()

    def set_select_mode(self):
        self.mode = "select"
        self.pending_text = None
        self.update()

    def set_text_mode(self, text=None):
        self.mode = "text"
        self.pending_text = text
        self.update()

    def set_erase_mode(self):
        self.mode = "erase"
        self.pending_text = None
        self.update()

    def clear(self):
        if not self.strokes and not self.text_items:
            return
        self.push_undo()
        self.strokes.clear()
        self.text_items.clear()
        self.selected_strokes.clear()
        self.selected_texts.clear()
        self.update()

    def set_pen_color(self, color):
        self.pen_color = QtGui.QColor(color)

class drawidaPlugin(ida_kernwin.PluginForm):
    def __init__(self, plugin_ref):
        super().__init__()
        self.plugin_ref = plugin_ref
        self.canvas = None

    def OnCreate(self, form):
        self.widget = self.FormToPyQtWidget(form)
        self.canvas = WhiteboardCanvas()
        
        layout = QtWidgets.QVBoxLayout()
        toolbar = QtWidgets.QToolBar()
        toolbar.setIconSize(QtCore.QSize(24, 24))

        draw_action = QtWidgets.QAction("Draw", self.widget)
        draw_action.triggered.connect(self.canvas.set_draw_mode)
        toolbar.addAction(draw_action)

        text_action = QtWidgets.QAction("Text", self.widget)
        text_action.triggered.connect(self.add_text)
        toolbar.addAction(text_action)

        select_action = QtWidgets.QAction("Select", self.widget)
        select_action.triggered.connect(self.canvas.set_select_mode)
        toolbar.addAction(select_action)

        erase_action = QtWidgets.QAction("Eraser", self.widget)
        erase_action.triggered.connect(self.canvas.set_erase_mode)
        toolbar.addAction(erase_action)

        toolbar.addSeparator()

        size_color_action = QtWidgets.QAction("Style", self.widget)
        size_color_action.triggered.connect(self.choose_sizes_dialog)
        toolbar.addAction(size_color_action)

        toolbar.addSeparator()

        undo_action = QtWidgets.QAction("Undo", self.widget)
        undo_action.triggered.connect(self.canvas.undo)
        toolbar.addAction(undo_action)

        redo_action = QtWidgets.QAction("Redo", self.widget)
        redo_action.triggered.connect(self.canvas.redo)
        toolbar.addAction(redo_action)

        toolbar.addSeparator()

        clear_action = QtWidgets.QAction("Clear", self.widget)
        clear_action.triggered.connect(self.on_clear)
        toolbar.addAction(clear_action)

        layout.addWidget(toolbar)
        layout.addWidget(self.canvas)
        layout.setContentsMargins(0, 0, 0, 0)
        self.widget.setLayout(layout)

    def add_text(self):
        text, ok = QtWidgets.QInputDialog.getText(self.widget, "Add Text", "Enter text:")
        if ok and text:
            self.canvas.set_text_mode(text)

    def choose_sizes_dialog(self):
        dialog = QtWidgets.QDialog(self.widget)
        dialog.setWindowTitle("Configure Style")
        layout = QtWidgets.QFormLayout(dialog)

        pen_input = QtWidgets.QSpinBox()
        pen_input.setRange(1, 50)
        pen_input.setValue(self.canvas.pen_size)

        text_input = QtWidgets.QSpinBox()
        text_input.setRange(6, 72)
        text_input.setValue(self.canvas.text_font_size)

        color_button = QtWidgets.QPushButton("Choose Color")
        selected_color = [self.canvas.pen_color]

        def pick_color():
            color = QtWidgets.QColorDialog.getColor(self.canvas.pen_color, dialog)
            if color.isValid():
                selected_color[0] = color
                color_button.setStyleSheet(f"background-color: {color.name()}; color: white;")

        color_button.clicked.connect(pick_color)
        color_button.setStyleSheet(f"background-color: {self.canvas.pen_color.name()}; color: white;")

        layout.addRow("Pen/Eraser Size:", pen_input)
        layout.addRow("Text Size:", text_input)
        layout.addRow("Color:", color_button)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        layout.addWidget(buttons)

        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)

        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            self.canvas.pen_size = pen_input.value()
            
            if self.canvas.selected_texts:
                for text in self.canvas.selected_texts:
                    text.font_size = text_input.value()
            
            self.canvas.text_font_size = text_input.value()
            self.canvas.pen_color = selected_color[0]
            self.canvas.update()

    def on_clear(self):
        if not self.canvas.strokes and not self.canvas.text_items:
            return
        
        self.canvas.clear()

    def OnClose(self, form):
        self.plugin_ref.form_instance = None
        self.canvas = None

class drawida_plugmod_t:
    def __init__(self):
        self.form_instance = None

    def show_form(self):
        if self.form_instance is None:
            self.form_instance = drawidaPlugin(self)
            self.form_instance.Show("DrawIDA")
        else:
            self.form_instance.widget.raise_()
            self.form_instance.widget.activateWindow()

class drawida_plugin_t(idaapi.plugin_t):
    flags = idaapi.PLUGIN_KEEP
    comment = "DrawIDA"
    help = "Whiteboard integrated in IDA"
    wanted_name = "DrawIDA"
    wanted_hotkey = "Ctrl-Shift-D"

    def init(self):
        self.mod = drawida_plugmod_t()
        ida_kernwin.msg("[DrawIDA] plugin loaded.\n")
        return idaapi.PLUGIN_OK

    def run(self, arg):
        self.mod.show_form()

    def term(self):
        ida_kernwin.msg("[DrawIDA] plugin terminated.\n")

def PLUGIN_ENTRY():
    return drawida_plugin_t()
