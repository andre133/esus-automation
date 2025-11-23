#!/bin/bash
echo "=== Forçando Python 3.11 ==="

# Instalar Python 3.11 explicitamente
pyenv install 3.11.8 -s
pyenv global 3.11.8

# Verificar versão
python --version

# Instalar dependências
pip install --upgrade pip
pip install -r requirements.txt

# Playwright
playwright install
playwright install-deps

echo "=== Build concluído ==="