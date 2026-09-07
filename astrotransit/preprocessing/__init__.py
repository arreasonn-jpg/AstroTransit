"""Ön işleme katmanı.

Light curve verilerini transit aramaya hazır hale getiren temizleme,
normalizasyon, detrending ve çok sektör stitching modülleri.
"""

from astrotransit.preprocessing.stitching import (
    StitchedDetrendedLightCurve,
    stitch_detrended_light_curves,
)

__all__ = ["StitchedDetrendedLightCurve", "stitch_detrended_light_curves"]
