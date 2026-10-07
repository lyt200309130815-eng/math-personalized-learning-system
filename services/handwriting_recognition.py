"""Future OCR boundary; intentionally offline and inactive in V1.0D."""


def recognize_math_image(image_path):
    return {'status':'not_implemented','image_path':str(image_path),
            'latex':None,'requires_user_confirmation':True}
