.PHONY: all win11 manifest clean clean-all

all: win11 manifest

win11:
	python3 win11/download_utils.py download
	python3 win11/download_utils.py extract
	python3 win11/win11_locales.py

manifest:
	python3 merge.py

clean-temp:
	python3 win11/download_utils.py clean

clean-all: clean-temp
	rm -rf win11/fonts win11/extraction.json win11/locales.json win11/fod-mapping.xlsx
	rm -rf fonts-merged fonts.yml families.json
