#!/bin/bash

# Remove migration directories from Git index
git rm --cached -r $(find . -type d -name 'migrations')

# Optional: Add .gitignore entry for migrations
if ! grep -q "*/migrations/" .gitignore; then
    echo "*/migrations/" >> .gitignore
fi

# Commit the changes
git add .gitignore
git commit -m "Add migration directories to .gitignore and remove from version control"
