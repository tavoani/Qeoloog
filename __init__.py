"""QGIS plugin entry point."""


def classFactory(iface):
    """Create the plugin instance for QGIS."""
    from .plugin import QeoloogPlugin

    return QeoloogPlugin(iface)
