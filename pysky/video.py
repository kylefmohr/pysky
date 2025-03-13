import imageio.v3 as iio

enable_video_operations = True


def get_aspect_ratio(video_filename):

    if not enable_video_operations:
        return None

    metadata = iio.immeta(video_filename)
    return metadata["size"]
