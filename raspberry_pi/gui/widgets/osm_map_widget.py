"""
Interactive OpenStreetMap Widget for KARP ADAS.
Uses QWebEngineView and Leaflet.js to render live OpenStreetMap tiles, vehicle marker, and GPS track.
"""

import json
from typing import Optional
from PySide6.QtCore import Qt, QUrl
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame, QHBoxLayout

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
    WEBENGINE_AVAILABLE = True
except ImportError:
    WEBENGINE_AVAILABLE = False


OSM_HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OpenStreetMap ADAS</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        html, body, #map {
            width: 100%;
            height: 100%;
            margin: 0;
            padding: 0;
            background-color: #0b0f15;
            font-family: 'Segoe UI', sans-serif;
        }
        /* Sleek automotive dark invert for OpenStreetMap tiles */
        .leaflet-tile-pane {
            filter: brightness(0.65) invert(1) contrast(3) hue-rotate(200deg) saturate(0.3) brightness(0.7);
        }
        #status-banner {
            position: absolute;
            top: 15px;
            left: 50%;
            transform: translateX(-50%);
            z-index: 1000;
            background: rgba(220, 38, 38, 0.9);
            color: #ffffff;
            padding: 8px 18px;
            border-radius: 6px;
            font-weight: bold;
            font-size: 13px;
            border: 1px solid #ff4444;
            letter-spacing: 1px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.5);
            display: block;
        }
        .vehicle-marker {
            width: 24px;
            height: 24px;
            background: #00D2FF;
            border: 3px solid #ffffff;
            border-radius: 50%;
            box-shadow: 0 0 14px #00D2FF;
        }
    </style>
</head>
<body>
    <div id="status-banner">GPS SIGNAL LOST / WAITING FOR SATELLITE FIX</div>
    <div id="map"></div>

    <script>
        var map = L.map('map', {
            zoomControl: true,
            attributionControl: false
        }).setView([20.0, 0.0], 2);

        L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 19
        }).addTo(map);

        var vehicleIcon = L.divIcon({
            className: 'vehicle-marker',
            iconSize: [20, 20],
            iconAnchor: [10, 10]
        });

        var marker = L.marker([0, 0], {icon: vehicleIcon, opacity: 0}).addTo(map);
        var trackPath = L.polyline([], {color: '#00D2FF', weight: 4, opacity: 0.8}).addTo(map);
        var isFirstFix = true;

        function updateVehicleLocation(lat, lon, heading, speed, hasFix) {
            var banner = document.getElementById('status-banner');
            if (!hasFix) {
                banner.style.display = 'block';
                banner.innerText = 'GPS SIGNAL LOST / NO SATELLITE FIX';
                marker.setOpacity(0.3);
                return;
            }

            banner.style.display = 'none';
            marker.setOpacity(1.0);
            marker.setLatLng([lat, lon]);
            trackPath.addLatLng([lat, lon]);

            if (isFirstFix) {
                map.setView([lat, lon], 16);
                isFirstFix = false;
            } else {
                map.panTo([lat, lon]);
            }
        }
    </script>
</body>
</html>
"""


class OpenStreetMapWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._has_fix = False
        self._lat = 0.0
        self._lon = 0.0
        self._speed = 0.0
        self._sats = 0

        if WEBENGINE_AVAILABLE:
            self.web_view = QWebEngineView()
            self.web_view.setHtml(OSM_HTML_TEMPLATE, QUrl("https://www.openstreetmap.org"))
            layout.addWidget(self.web_view)
        else:
            # Fallback label if WebEngine is unavailable
            from raspberry_pi.gui.widgets.map_widget import MapWidget
            self.fallback_widget = MapWidget()
            layout.addWidget(self.fallback_widget)
            self.web_view = None

    def update_gps(
        self,
        lat: float,
        lon: float,
        alt: float,
        speed: float,
        heading: float,
        sats: int,
        fix: int,
        is_sim: bool,
    ) -> None:
        self._lat = lat
        self._lon = lon
        self._speed = speed
        self._sats = sats
        self._has_fix = (fix > 0) or is_sim

        if self.web_view is not None:
            has_fix_js = "true" if self._has_fix else "false"
            js_code = f"if (typeof updateVehicleLocation === 'function') {{ updateVehicleLocation({lat}, {lon}, {heading}, {speed}, {has_fix_js}); }}"
            self.web_view.page().runJavaScript(js_code)
        elif hasattr(self, "fallback_widget"):
            self.fallback_widget.update_gps(lat, lon, alt, speed, heading, sats, fix, is_sim)
