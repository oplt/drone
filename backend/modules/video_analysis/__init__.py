"""Offline drone video analysis module.

This module owns uploaded/recorded video assets, analysis jobs, frame inference,
and detection persistence. Domain-specific consumers such as irrigation can read
its detections or subscribe to completion events later.
"""
