from __future__ import annotations

import logging
import platform
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from numpy.typing import NDArray

from billetvision import config
from billetvision.enums import SourceType
from billetvision.schemas import SourceInfo
from billetvision.vision.synth import (
    CameraSpec,
    Effects,
    SceneSpec,
    render_scene,
    render_video,
)

logger = logging.getLogger(__name__)


class FrameSource(ABC):
    """Abstract interface for all video and frame capture sources."""

    @abstractmethod
    def open(self) -> bool:
        """Open or initialize the source. Returns True on success."""
        ...

    @abstractmethod
    def read(self) -> tuple[NDArray[np.uint8], float] | None:
        """Read the latest frame. Returns (frame_bgr, t_monotonic) or None."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Release underlying camera or stream resources."""
        ...

    @abstractmethod
    def info(self) -> SourceInfo:
        """Return metadata about current capture source."""
        ...

    def empty_frame(self) -> NDArray[np.uint8] | None:
        """Return an empty background frame (supported by synthetic source)."""
        return None


class WebcamSource(FrameSource):
    """Local USB or built-in webcam capture source."""

    def __init__(self, device_index: int = 0) -> None:
        self.device_index = device_index
        self.cap: cv2.VideoCapture | None = None
        self.driver_properties: dict[str, Any] = {}
        self._actual_width: int | None = None
        self._actual_height: int | None = None
        self._actual_fps: float | None = None

    def open(self) -> bool:
        self.close()

        # DirectShow on Windows, default API on Mac/Linux
        backend = cv2.CAP_DSHOW if platform.system() == "Windows" else cv2.CAP_ANY
        self.cap = cv2.VideoCapture(self.device_index, backend)
        if not self.cap.isOpened():
            logger.warning("Failed to open webcam at index %s", self.device_index)
            self.cap = None
            return False

        # Request resolution & FPS
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.FRAME_WIDTH)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.FRAME_HEIGHT)
        self.cap.set(cv2.CAP_PROP_FPS, config.CAPTURE_FPS)

        # Attempt to lock exposure, focus, white balance
        self.driver_properties = self._attempt_driver_locks()

        # Read back actual granted values
        self._actual_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self._actual_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self._actual_fps = float(self.cap.get(cv2.CAP_PROP_FPS))

        logger.info(
            "Webcam %s opened: granted %sx%s @ %.1f FPS. Driver properties: %s",
            self.device_index,
            self._actual_width,
            self._actual_height,
            self._actual_fps,
            self.driver_properties,
        )
        return True

    def _attempt_driver_locks(self) -> dict[str, Any]:
        """Try locking exposure, focus, and WB, reporting what the driver accepted."""
        if self.cap is None:
            return {}

        props: dict[str, Any] = {}

        # 1. Exposure
        try:
            # Setting 1 or 0.25 disables auto-exposure depending on OS backend
            self.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 1.0)
            val = self.cap.get(cv2.CAP_PROP_AUTO_EXPOSURE)
            props["auto_exposure_locked"] = bool(val == 1.0)
        except Exception:
            props["auto_exposure_locked"] = False

        # 2. Focus
        try:
            self.cap.set(cv2.CAP_PROP_AUTOFOCUS, 0.0)
            val = self.cap.get(cv2.CAP_PROP_AUTOFOCUS)
            props["autofocus_locked"] = bool(val == 0.0)
        except Exception:
            props["autofocus_locked"] = False

        # 3. White balance
        try:
            self.cap.set(cv2.CAP_PROP_AUTO_WB_TEMPERATURE, 0.0)
            val = self.cap.get(cv2.CAP_PROP_AUTO_WB_TEMPERATURE)
            props["auto_wb_locked"] = bool(val == 0.0)
        except Exception:
            props["auto_wb_locked"] = False

        return props

    def read(self) -> tuple[NDArray[np.uint8], float] | None:
        if self.cap is None or not self.cap.isOpened():
            return None
        ret, frame = self.cap.read()
        t = time.monotonic()
        if not ret or frame is None or frame.size == 0:
            return None
        return frame, t

    def close(self) -> None:
        if self.cap is not None:
            self.cap.release()
            self.cap = None

    def info(self) -> SourceInfo:
        return SourceInfo(
            type=SourceType.webcam,
            value=str(self.device_index),
            frame_width=self._actual_width,
            frame_height=self._actual_height,
        )


class UrlSource(FrameSource):
    """Network camera source (MJPEG / RTSP / phone IP webcam)."""

    def __init__(self, url: str) -> None:
        self.url = url
        self.cap: cv2.VideoCapture | None = None
        self._actual_width: int | None = None
        self._actual_height: int | None = None

    def open(self) -> bool:
        self.close()
        self.cap = cv2.VideoCapture(self.url)
        if not self.cap.isOpened():
            logger.warning("Failed to open URL stream: %s", self.url)
            self.cap = None
            return False
        self._actual_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self._actual_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        logger.info("URL stream opened (%sx%s): %s", self._actual_width, self._actual_height, self.url)
        return True

    def read(self) -> tuple[NDArray[np.uint8], float] | None:
        if self.cap is None or not self.cap.isOpened():
            return None
        ret, frame = self.cap.read()
        t = time.monotonic()
        if not ret or frame is None or frame.size == 0:
            return None
        return frame, t

    def close(self) -> None:
        if self.cap is not None:
            self.cap.release()
            self.cap = None

    def info(self) -> SourceInfo:
        return SourceInfo(
            type=SourceType.url,
            value=self.url,
            frame_width=self._actual_width,
            frame_height=self._actual_height,
        )


class FileSource(FrameSource):
    """Video file playback source, paced at CAPTURE_FPS with loop-on-EOF."""

    def __init__(self, file_path: str | Path, fps: int = config.CAPTURE_FPS) -> None:
        self.file_path = Path(file_path).resolve()
        self.target_fps = fps
        self.cap: cv2.VideoCapture | None = None
        self._frame_interval_s = 1.0 / max(fps, 1)
        self._last_read_t = 0.0
        self._actual_width: int | None = None
        self._actual_height: int | None = None

    def open(self) -> bool:
        self.close()
        if not self.file_path.is_file():
            logger.warning("Video file not found: %s", self.file_path)
            return False
        self.cap = cv2.VideoCapture(str(self.file_path))
        if not self.cap.isOpened():
            self.cap = None
            return False
        self._actual_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self._actual_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self._last_read_t = time.monotonic()
        logger.info("FileSource opened: %s", self.file_path)
        return True

    def read(self) -> tuple[NDArray[np.uint8], float] | None:
        if self.cap is None or not self.cap.isOpened():
            return None

        # Pace to target FPS
        now = time.monotonic()
        elapsed = now - self._last_read_t
        if elapsed < self._frame_interval_s:
            time.sleep(self._frame_interval_s - elapsed)

        ret, frame = self.cap.read()
        t = time.monotonic()
        self._last_read_t = t

        # Loop on EOF
        if not ret or frame is None:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = self.cap.read()
            if not ret or frame is None:
                return None

        return frame, t

    def close(self) -> None:
        if self.cap is not None:
            self.cap.release()
            self.cap = None

    def info(self) -> SourceInfo:
        return SourceInfo(
            type=SourceType.file,
            value=str(self.file_path),
            frame_width=self._actual_width,
            frame_height=self._actual_height,
        )


class SyntheticSource(FrameSource):
    """Continuous synthetic inspection station generator loop."""

    def __init__(
        self,
        mode: str = "station",
        fps: int = config.CAPTURE_FPS,
        seed: int = config.SEED,
    ) -> None:
        self.mode = mode
        self.target_fps = fps
        self.seed = seed
        self._frame_interval_s = 1.0 / max(fps, 1)
        self._last_read_t = 0.0
        self._frame_generator: Any = None
        self._is_open: bool = False

    def open(self) -> bool:
        self.close()
        rng = np.random.default_rng(self.seed)
        mode = "station" if self.mode == "station" else "conveyor"
        self._frame_generator = render_video(
            rng=rng,
            mode=mode,
            n_billets=500,
            fps=self.target_fps,
        )
        self._is_open = True
        self._last_read_t = time.monotonic()
        logger.info("SyntheticSource opened (mode=%s, fps=%s)", self.mode, self.target_fps)
        return True

    def read(self) -> tuple[NDArray[np.uint8], float] | None:
        gen = self._frame_generator
        if not self._is_open or gen is None:
            return None

        now = time.monotonic()
        elapsed = now - self._last_read_t
        if elapsed < self._frame_interval_s:
            time.sleep(self._frame_interval_s - elapsed)

        try:
            gen = self._frame_generator
            if gen is None:
                return None
            frame, _ = next(gen)
        except (StopIteration, TypeError):
            if not self._is_open:
                return None
            self.open()
            if self._frame_generator is None:
                return None
            frame, _ = next(self._frame_generator)

        t = time.monotonic()
        self._last_read_t = t
        return frame, t

    def empty_frame(self) -> NDArray[np.uint8]:
        """Generate a clean empty station scene with marker for auto-calibration."""
        rng = np.random.default_rng(self.seed)
        scene = SceneSpec(
            billets=(),
            camera=CameraSpec(),
            effects=Effects(),
            with_marker=True,
        )
        img, _ = render_scene(scene, rng)
        return img

    def close(self) -> None:
        self._is_open = False
        self._frame_generator = None

    def info(self) -> SourceInfo:
        return SourceInfo(
            type=SourceType.synthetic,
            value=self.mode,
            frame_width=config.FRAME_WIDTH,
            frame_height=config.FRAME_HEIGHT,
        )


def make_source(source_type: str | SourceType, value: str = "") -> FrameSource:
    """Factory creating appropriate FrameSource instance from type and value."""
    st = str(source_type).lower()
    if st == SourceType.webcam.value:
        dev_idx = int(value) if value.strip().isdigit() else 0
        return WebcamSource(dev_idx)
    if st == SourceType.url.value:
        return UrlSource(value)
    if st == SourceType.file.value:
        return FileSource(value)
    return SyntheticSource(mode="station")
