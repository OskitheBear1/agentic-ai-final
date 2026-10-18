#!/bin/sh
cp scripts/secret_scan.sh .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit && echo "pre-commit secret scan installed"
