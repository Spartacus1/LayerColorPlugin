import os
from qgis.core import QgsMessageLog, Qgis, QgsProject

try:
  from qgis.gui import QgsLayerTreeViewItemDelegate
  has_QgsLayerTreeViewItemDelegate = True
except:
  # QgsLayerTreeViewItemDelegate isn't exported
  # Will fall back to using QStyledItemDelegate
  has_QgsLayerTreeViewItemDelegate = False

from PyQt5.QtWidgets import QColorDialog, QAction, QMenu, QStyledItemDelegate
from PyQt5.QtGui import QColor, QPainter, QIcon
from PyQt5.QtCore import Qt

def log_message(message):
    """
    "Sends messages to the QGIS log panel and the Python console".
    """
    QgsMessageLog.logMessage(message, "LayerColorPlugin", Qgis.Info)
    print(message)  # Shows in the Python console


class LayerColorPlugin:
    clipboard_color = None  # Variable to store the copied color

    def copy_highlight_color(self):
        selected_nodes = self.layer_tree_view.selectedNodes()
        if not selected_nodes:
            log_message("No layer or group selected to copy the color.")
            return

        node = selected_nodes[0]
        node_name = node.name()
        color = self.layer_colors.get(node_name)
        if color:
            LayerColorPlugin.clipboard_color = color
            log_message(f"Cor '{color}' copied to the clipboard.")
        else:
            log_message("No color assigned to the selected item.")

    def paste_highlight_color(self):
        if not LayerColorPlugin.clipboard_color:
            log_message("No color available on the clipboard to paste.")
            return
    
        selected_nodes = self.layer_tree_view.selectedNodes()
        if not selected_nodes:
            log_message("No layer or group selected to paste the color.")
            return
    
        # Aplicar a cor a todos os nós selecionados
        for node in selected_nodes:
            node_name = node.name()
            self.layer_colors[node_name] = LayerColorPlugin.clipboard_color
            node.setCustomProperty("highlight_color", LayerColorPlugin.clipboard_color)  # Keep the color
            log_message(f"Cor '{LayerColorPlugin.clipboard_color}' pasted in item '{node_name}'.")
    
        # Update the visualization only once after applying to all layers
        self.layer_tree_view.viewport().update()
        
        
    def __init__(self, iface):
        self.iface = iface
        self.layer_colors = {}
        self.plugin_dir = os.path.dirname(__file__)

    def initGui(self):
        try:
            self.layer_tree_view = self.iface.layerTreeView()
            if not self.layer_tree_view:
                raise Exception("Layer Tree View not available")
            
            # Delegate customized
            self.delegate = LayerColorDelegate(self.layer_colors, self.layer_tree_view)
            self.layer_tree_view.setItemDelegate(self.delegate)

            # Connect signal from the context menu
            self.layer_tree_view.setContextMenuPolicy(Qt.CustomContextMenu)
            self.layer_tree_view.customContextMenuRequested.connect(self.show_context_menu)

            # Connect to the project save event
            QgsProject.instance().writeProject.connect(self.save_colors)

            # Connect to the project load event
            self.iface.projectRead.connect(self.load_colors)

            # Load initial colors if the project is already loaded
            if self.iface.activeLayer():
                self.load_colors()

        except Exception as e:
            log_message(f"Error during plugin initialization: {str(e)}")

    def unload(self):
        try:
            # Disconnect signal from the context menu
            if hasattr(self, "layer_tree_view"):
                self.layer_tree_view.customContextMenuRequested.disconnect(self.show_context_menu)

            # Restore the original delegate
            if hasattr(self, "delegate") and self.delegate is not None:
                if has_QgsLayerTreeViewItemDelegate:
                    original_delegate = QgsLayerTreeViewItemDelegate(self.layer_tree_view)
                else:
                    original_delegate = QStyledItemDelegate(self.layer_tree_view)
                self.layer_tree_view.setItemDelegate(original_delegate)
                self.delegate = None

            # Disconnect signals
            QgsProject.instance().writeProject.disconnect(self.save_colors)
            self.iface.projectRead.disconnect(self.load_colors)

            # Clear color dictionary
            if hasattr(self, "layer_colors"):
                self.layer_colors.clear()

            # Update interface
            if hasattr(self, "layer_tree_view"):
                self.layer_tree_view.viewport().update()

        except Exception as e:
            log_message(f"Erro durante unload: {str(e)}")

    def show_context_menu(self, point):
        # Temporarily disconnect the signal
        self.layer_tree_view.customContextMenuRequested.disconnect(self.show_context_menu)
    
        # Create the custom context menu
        context_menu = QMenu(self.layer_tree_view)
    
        # Retrieve the default QGIS actions (if available)
        default_menu_provider = self.layer_tree_view.menuProvider()
        if default_menu_provider:
            default_menu = default_menu_provider.createContextMenu()
            if default_menu:
                context_menu.addActions(default_menu.actions())
    
        # Create the custom submenu
        highlight_menu = QMenu("Layer Highlight Color", context_menu)
    
        set_color_action = QAction("Set Background Color", highlight_menu)
        set_color_action.triggered.connect(self.set_layer_color)
        highlight_menu.addAction(set_color_action)
    
        remove_color_action = QAction("Remove Background Color", highlight_menu)
        remove_color_action.triggered.connect(lambda: self.handle_remove_color(context_menu))
        highlight_menu.addAction(remove_color_action)
        
        copy_color_action = QAction("Copy Highlight Color", highlight_menu)
        copy_color_action.triggered.connect(lambda: self.handle_copy_color(context_menu))
        highlight_menu.addAction(copy_color_action)
        
        paste_color_action = QAction("Paste Highlight Color", highlight_menu)
        paste_color_action.triggered.connect(lambda: self.handle_paste_color(context_menu))
        highlight_menu.addAction(paste_color_action)
    
        # Insert the submenu before "Properties"
        actions = context_menu.actions()
        if actions:
            context_menu.insertMenu(actions[-1], highlight_menu)
        else:
            context_menu.addMenu(highlight_menu)
    
        # Display the context menu and reconnect the signal afterward
        context_menu.aboutToHide.connect(
            lambda: self.layer_tree_view.customContextMenuRequested.connect(self.show_context_menu)
        )
        context_menu.exec_(self.layer_tree_view.mapToGlobal(point))
        
    def handle_remove_color(self, context_menu):
        self.remove_layer_color()
        context_menu.close()
            
    def handle_copy_color(self, menu):
        self.copy_highlight_color()
        menu.close()
        
    def handle_paste_color(self, menu):
        self.paste_highlight_color()
        menu.close()
        
    def calculate_contrast_ratio(self, background_color):
        """
        Calculate the contrast ratio between the background color and black text
        following the WCAG 2.0 guidelines
        """
        bg_color = QColor(background_color)
        
        # Convert RGB to relative luminance
        def get_luminance(r, g, b):
            # Normalize RGB values
            rs = r / 255
            gs = g / 255
            bs = b / 255
            
            # Convert to sRGB
            rs = rs / 12.92 if rs <= 0.03928 else ((rs + 0.055) / 1.055) ** 2.4
            gs = gs / 12.92 if gs <= 0.03928 else ((gs + 0.055) / 1.055) ** 2.4
            bs = bs / 12.92 if bs <= 0.03928 else ((bs + 0.055) / 1.055) ** 2.4
            
            return 0.2126 * rs + 0.7152 * gs + 0.0722 * bs
    
        # Calculate the luminance of the background and the text (black)
        bg_luminance = get_luminance(bg_color.red(), bg_color.green(), bg_color.blue())
        text_luminance = get_luminance(0, 0, 0)  # Black
    
        # Calculate the contrast ratio
        lighter = max(bg_luminance, text_luminance)
        darker = min(bg_luminance, text_luminance)
        
        return (lighter + 0.05) / (darker + 0.05)        

    def set_layer_color(self):
        selected_nodes = self.layer_tree_view.selectedNodes()
        if not selected_nodes:
            return
    
        # Open the color dialog only once
        color = QColorDialog.getColor()
        if color.isValid():
            # Check contrast
            contrast_ratio = self.calculate_contrast_ratio(color.name())
            
            # If the contrast is low (less than 4.5, which is the WCAG AA standard)
            if contrast_ratio < 4.5:
                from PyQt5.QtWidgets import QMessageBox
                from PyQt5.QtCore import Qt
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Warning)
                msg.setText("<h3>Contrast Warning</h3>")  # Using HTML for bigger text
                msg.setInformativeText("""
                    <p style='font-size: 12pt; margin: 12px 0; font-weight: bold;'>
                    According to "WCAG AA (4.5:1)" Standard, the selected color may make the text difficult to read.
                    </p>
                    <p style='font-size: 12pt; font-weight: bold;'>
                    Do you want to continue anyway?
                    </p>
                """)
                msg.setWindowTitle("Layer Color Plugin")
                
                # Define minimun window size
                msg.setMinimumWidth(480)
                
                # Config buttons
                msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
                msg.setDefaultButton(QMessageBox.No)
                
                # Adjust window flags
                msg.setWindowFlags(msg.windowFlags() | Qt.WindowStaysOnTopHint)
                
                if msg.exec_() == QMessageBox.No:
                    return
    
            # Apply the color to all selected nodes
            for layer in selected_nodes:
                layer_name = layer.name()
                self.layer_colors[layer_name] = color.name()
                layer.setCustomProperty("highlight_color", color.name())  # Persist the color
                log_message(f"Camada ou grupo: {layer_name}, Cor atribuída: {color.name()}")
            
            # Update the visualization only once after applying to all layers
            self.layer_tree_view.viewport().update()
                

    def remove_layer_color(self):
        selected_nodes = self.layer_tree_view.selectedNodes()
        if not selected_nodes:
            return
    
        # Remove the color from all selected nodes
        for layer in selected_nodes:
            layer_name = layer.name()
            if layer_name in self.layer_colors:
                del self.layer_colors[layer_name]
                layer.removeCustomProperty("highlight_color")  # Remove the persistent property
                log_message(f"Color removed from the layer or group: {layer_name}")
        
        # Update the visualization only once after removing from all layers
        self.layer_tree_view.viewport().update()

    def save_colors(self):
        try:
            def save_node_colors(node):
                if hasattr(node, "customProperty"):
                    name = node.name()
                    color = self.layer_colors.get(name)
                    if color:
                        node.setCustomProperty("highlight_color", color)
                        log_message(f"Saving color '{color}' para '{name}'")
                
                # Recursivamente processa os filhos
                for child in node.children():
                    save_node_colors(child)
                    
            root = self.iface.layerTreeView().layerTreeModel().rootGroup()
            save_node_colors(root)
            log_message("All colors were successfully saved in the project.")
        except Exception as e:
            log_message(f"Error while saving colors: {str(e)}")

    def load_colors(self):
        self.layer_colors.clear()
        try:
            def load_node_colors(node):
                if hasattr(node, "customProperty"):
                    color = node.customProperty("highlight_color")
                    if color:
                        self.layer_colors[node.name()] = color
                        log_message(f"Cor '{color}' loaded for '{node.name()}'")
                
                for child in node.children():
                    load_node_colors(child)
                    
            root = self.iface.layerTreeView().layerTreeModel().rootGroup()
            load_node_colors(root)
            self.layer_tree_view.viewport().update()
            log_message("All colors were successfully restored.")
        except Exception as e:
            log_message(f"Error loading colors: {str(e)}")


if has_QgsLayerTreeViewItemDelegate:
  delegateClass = QgsLayerTreeViewItemDelegate
else:
  delegateClass = QStyledItemDelegate

class LayerColorDelegate( delegateClass ):
    def __init__(self, layer_colors, parent=None):
        super().__init__(parent)
        self.layer_colors = layer_colors

    def paint(self, painter, option, index):
        layer_name = index.data(Qt.DisplayRole)
        if layer_name in self.layer_colors:
            painter.save()
            color = QColor(self.layer_colors[layer_name])
            painter.fillRect(option.rect, color)
            painter.restore()

        super().paint(painter, option, index)

# Renato Henriques - Universidade do Minho/Instituto de Ciências da Terra