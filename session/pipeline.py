import gi

gi.require_version("Gst", "1.0")
from gi.repository import Gst


def pipeline_init():
    Gst.init()
