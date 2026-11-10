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
    from PIL import Image
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
    except (ValueError, OSError):
        return False
    return True
