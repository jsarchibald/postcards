CREATE TABLE "source_images" (
	"id"	INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
	"image"	BLOB NOT NULL
);

CREATE TABLE "postcards" (
	"id"	INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
	"name"	INTEGER NOT NULL,
	"text_alignment"	CHAR(2) NOT NULL,
	"source_image_id"	INTEGER NOT NULL REFERENCES source_images(id),
	"image"	BLOB NOT NULL
);