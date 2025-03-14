import mimetypes

# for compatibility with python < 3.13
guess_file_type = getattr(mimetypes, "guess_file_type", mimetypes.guess_type)
