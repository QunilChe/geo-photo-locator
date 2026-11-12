import piexif, logging
logger = logging.getLogger(__name__)

def _deg_to_dms(deg):
    d = int(abs(deg))
    m = int((abs(deg) - d) * 60)
    s = (abs(deg) - d - m/60) * 3600
    return ((d, 1), (m, 1), (int(s * 100), 100))

def write_gps_to_exif(image_path, latitude, longitude):
    try:
        try:
            exif_dict = piexif.load(image_path)
        except Exception:
            exif_dict = {'0th': {}, 'Exif': {}, 'GPS': {}, '1st': {}, 'thumbnail': None}
        exif_dict['GPS'][piexif.GPSIFD.GPSVersionID] = (2, 0, 0, 0)
        exif_dict['GPS'][piexif.GPSIFD.GPSLatitudeRef]  = 'N' if latitude  >= 0 else 'S'
        exif_dict['GPS'][piexif.GPSIFD.GPSLatitude]     = _deg_to_dms(latitude)
        exif_dict['GPS'][piexif.GPSIFD.GPSLongitudeRef] = 'E' if longitude >= 0 else 'W'
        exif_dict['GPS'][piexif.GPSIFD.GPSLongitude]    = _deg_to_dms(longitude)
        piexif.insert(piexif.dump(exif_dict), image_path)
        logger.info(f'GPS записано в {image_path}')
        return True
    except Exception as e:
        logger.error(f'EXIF помилка: {e}')
        return False
