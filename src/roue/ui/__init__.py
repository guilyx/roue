"""GTK 4 + libadwaita front end. Imported lazily: the CLI works without it."""

import gi

# Pin versions before anything imports gi.repository.Gtk/Adw.
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
