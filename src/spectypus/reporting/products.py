"""Atlas-only raster product contract; independent of general plot exports."""
from pathlib import Path

from spectypus.io import file_hash

PLOT_OUTPUT = {'formats': ['jpg'], 'dpi': 300}


def save_jpg(fig, stem):
    stem = Path(stem)
    if stem.suffix.lower() in {'.pdf', '.jpg', '.jpeg', '.png'}:
        raise ValueError('Pass an output stem without an image extension')
    stem.parent.mkdir(parents=True, exist_ok=True)
    path = Path(str(stem) + '.jpg')
    fig.savefig(path, dpi=300, format='jpg', bbox_inches='tight')
    return path


def validate_jpg(path):
    try:
        from PIL import Image
    except ImportError:
        # Reading an already hash-verified master does not need a plotting
        # installation. Matplotlib exports JFIF with density in dots/inch.
        data = path.read_bytes()
        if not data.startswith(b'\xff\xd8') or not data.endswith(b'\xff\xd9'):
            raise ValueError(f'Expected a complete JPEG: {path}')
        offset = 2
        while offset + 4 <= len(data):
            marker = data[offset:offset + 2]
            size = int.from_bytes(data[offset + 2:offset + 4], 'big')
            if size < 2 or offset + 2 + size > len(data):
                break
            chunk = data[offset + 4:offset + 2 + size]
            if marker == b'\xff\xe0' and chunk.startswith(b'JFIF\x00'):
                if len(chunk) >= 12 and chunk[7] == 1 and chunk[8:12] == b'\x01,\x01,':
                    return
                break
            offset += 2 + size
        raise ValueError(f'Expected 300-dpi JFIF JPEG: {path}')
    with Image.open(path) as image:
        if image.format != 'JPEG' or image.info.get('dpi') != (300, 300):
            raise ValueError(f'Expected 300-dpi JPEG: {path}')
        image.verify()


def validate_product(folder, result):
    if 'pdf' in result or set(result.get('product_hashes', {})) != {'jpg'}:
        raise ValueError('Expected JPG-only product hashes')
    name = result.get('jpg', '')
    path = folder / name
    if not name or Path(name).name != name or Path(name).suffix != '.jpg':
        raise ValueError('Invalid JPG product path')
    if file_hash(path) != result['product_hashes']['jpg']:
        raise ValueError(f'Changed JPG product: {path}')
    validate_jpg(path)


def product_ready(folder, result):
    if result.get('status') != 'ready':
        return False
    try:
        validate_product(folder, result)
    except (ValueError, OSError, ImportError):
        return False
    return True
