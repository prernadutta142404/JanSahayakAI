"""Safe, local OCR and video-frame extraction with optional-dependency fallbacks."""
from __future__ import annotations
from pathlib import Path
import io
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
def validate_upload(filename: str, size: int) -> tuple[bool, str]:
    ext = Path(filename or "").suffix.lower()
    if size <= 0: return False, "The uploaded file is empty."
    if size > MAX_UPLOAD_BYTES: return False, "File exceeds the 25 MB limit."
    if ext not in IMAGE_EXTS | VIDEO_EXTS: return False, "Unsupported file type. Use a common image or video format."
    return True, "Accepted format."
def analyze_image(data: bytes, filename: str) -> dict:
    ok, message = validate_upload(filename, len(data))
    if not ok or Path(filename).suffix.lower() not in IMAGE_EXTS:
        return {"filename": Path(filename).name, "status": "failed", "text": "", "message": message if not ok else "This is not a supported image."}
    try:
        from PIL import Image
        import pytesseract

        # Configure Tesseract for Windows
        tesseract_path = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
        if tesseract_path.exists():
            pytesseract.pytesseract.tesseract_cmd = str(tesseract_path)

        image = Image.open(io.BytesIO(data)).convert("RGB")
        text = pytesseract.image_to_string(image)
        return {"filename": Path(filename).name, "status": "complete" if text.strip() else "no_text_found",
                "text": text.strip(), "message": "Review extracted text; OCR can be inaccurate."}
    except ImportError:
        return {"filename": Path(filename).name, "status": "unavailable", "text": "",
                "message": "OCR dependencies are unavailable. Install Pillow, pytesseract and the Tesseract executable."}
    except Exception:
        return {"filename": Path(filename).name, "status": "failed", "text": "",
                "message": "Image could not be processed. Check that the file is a valid image and Tesseract is installed."}
def extract_video_frames(data: bytes, filename: str, max_frames: int = 5) -> dict:
    ok, message = validate_upload(filename, len(data))
    if not ok or Path(filename).suffix.lower() not in VIDEO_EXTS:
        return {"filename": Path(filename).name, "status": "failed", "frames": [], "message": message if not ok else "This is not a supported video."}
    temp_path = None
    try:
        import cv2, tempfile
        with tempfile.NamedTemporaryFile(suffix=Path(filename).suffix, delete=False) as temp:
            temp.write(data); temp_path = temp.name
        cap = cv2.VideoCapture(temp_path)
        if not cap.isOpened():
            cap.release()
            return {"filename": Path(filename).name, "status": "failed", "frames": [], "message": "Video could not be opened."}
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        frames = []
        indices = sorted(set(int(i * max(total - 1, 0) / max(max_frames - 1, 1)) for i in range(min(max_frames, max(total, 1)))))
        for index in indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, index)
            success, frame = cap.read()
            if success:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                from PIL import Image
                buf = io.BytesIO(); Image.fromarray(rgb).save(buf, format="JPEG")
                frames.append({"frame_index": index, "jpeg_bytes": buf.getvalue()})
        cap.release()
        return {"filename": Path(filename).name, "status": "complete" if frames else "failed",
                "frames": frames, "message": f"Extracted {len(frames)} selected frame(s); no damage recognition is performed."}
    except ImportError:
        return {"filename": Path(filename).name, "status": "unavailable", "frames": [],
                "message": "Video dependencies unavailable. Install opencv-python and Pillow."}
    except Exception:
        return {"filename": Path(filename).name, "status": "failed", "frames": [],
                "message": "Video processing failed. Try another supported video file."}
    finally:
        if temp_path:
            try: Path(temp_path).unlink(missing_ok=True)
            except OSError: pass
