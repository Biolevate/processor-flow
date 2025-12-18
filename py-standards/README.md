# py-standards

Collection of Python standards.

## Usage

Add this repository as a submodule to your Python project.

```bash
git submodule add git@github.com:Biolevate/py-standards.git
```

### `ruff.toml`

- **What is it?**

  A simple, opinionated configuration file for `ruff`, a linting and formatting tool.

- **What is the spirit?**

  Enforce best practice, and share formatting rules such as line length.
  In the future, CI will run a check against the rules set in this file.

- **How to use it?**

  See <https://docs.astral.sh/ruff/editors/setup/> to set up your editor. You will want to configure formatting on save.

  Put this in your `pyproject.toml`:

  ```toml
  [tool.ruff]
  extend = "./py-standards/ruff.toml"
  ```

  *Override* some rules such as line length as follows:

  ```toml
  [tool.ruff]
  extend = "./py-standards/ruff.toml"
  line-length = 140
  ```

  *Extend* rules as follows; DO NOT use plain `select` or `ignore` as it will *override* this configuration!

  Don't do this:

  ```toml
  [tool.ruff.lint]
  select = ["ALL"] # DO NOT USE plain `select`
  ignore = [
    # some rules...
  ]
  ```

  Instead, do this:

  ```toml
  [tool.ruff.lint]
  extend-select = ["ALL"]
  extend-ignore = [
    "E501",     # line too long
    "TD",       # invalid todos
    "S311",     # suspicious non cryptographic random usage
    "FBT",      # boolean trap
    "ERA",      # found commented-out code
    "T20",      # (p)print found
    "G004",     # logging statement using f-string
    "PLR0913",  # too many arguments
  ]
  ```

- **Reference**

  See <https://docs.astral.sh/ruff/rules/>
