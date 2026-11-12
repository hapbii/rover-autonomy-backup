# Provenance correction

The existing sibling yolo_dataset directory contained 565 images and matching four-class labels.
The assistant incorrectly described them as labels supplied by the user for this rover project.
On 2026-11-12 the user clarified that no such project photos or annotations had been supplied.
The origin/author and applicability of those existing files are UNVERIFIED.
Earlier crop/full-frame metrics were development results on that directory, not proof of this robot or a new scene.
Those trained weights, derived image fixtures and reports are archived here for audit, excluded from the default ROS package and Pi distribution.
The original sibling dataset has not been changed.
The default sign detector now uses untrained color/geometry and synthetic graphics for functional tests only.
No real-camera sign accuracy has been established.
