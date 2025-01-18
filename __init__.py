from .layer_color_plugin import LayerColorPlugin

def classFactory(iface):
    return LayerColorPlugin(iface)
