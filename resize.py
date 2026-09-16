from PIL import Image

src = r"C:\Users\Cyrus\Downloads\New folder (33)\New folder (32)\Main1\md\drive\previews\IMG_1225.jpg"
dst = r"C:\Users\Cyrus\Downloads\New folder (72)\Inscrona\test_resized.jpg"

img = Image.open(src)
print(f"Original: {img.size}")
img.thumbnail((2000, 2000), Image.LANCZOS)
print(f"Resized: {img.size}")
img.save(dst, quality=85)
print("Saved test_resized.jpg")
