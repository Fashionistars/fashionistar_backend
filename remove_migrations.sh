#!/bin/bash

# Find migration directories and remove their files from Git index if they exist
find . -type d -name 'migrations' | while read -r dir; do
  # Check if the directory contains files tracked by Git
  if git ls-files --error-unmatch "$dir"/* >/dev/null 2>&1; then
    # Remove files inside the migration directory from Git index
    git rm --cached "$dir"/*
  else
    echo "No tracked files in $dir"
  fi
done

# Optional: Add .gitignore entry for migrations if not already present
if ! grep -q "*/migrations/" .gitignore; then
  echo "*/migrations/" >> .gitignore
fi

git add .gitignore
git commit -m "Add migration files to .gitignore and remove from version control"
