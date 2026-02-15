.PHONY: all win11 merge clean clean-all

all: win11 merge

win11:
	python3 win11/download_utils.py download
	python3 win11/download_utils.py extract

build-locales:
	python3 win11/win11_locales.py
	python3 ubuntu/ubuntu_locales.py

merge: build-locales
	python3 merge.py

clean-temp:
	python3 win11/download_utils.py clean

clean: clean-temp
	rm -rf merged fonts.yml families.json families.min.json

clean-all: clean
	rm -rf win11/fonts win11/fod-mapping.xlsx win11/extraction.json win11/locales.json ubuntu/locales.json
