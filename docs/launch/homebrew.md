# Publishing the Homebrew tap

One-time setup, after the repo is pushed and tagged.

## 1. Tag a release

```bash
cd ~/Documents/macsweep
git tag v0.2.0 && git push origin main --tags
gh release create v0.2.0 --title "v0.2.0" --notes-file CHANGELOG.md
```

## 2. Create the tap repository

Create a new GitHub repo named exactly `homebrew-macsweep` (the `homebrew-` prefix is required), containing `Formula/macsweep.rb`:

```ruby
class Macsweep < Formula
  include Language::Python::Virtualenv

  desc "Safe, whitelist-only storage cleaner for macOS - never needs sudo"
  homepage "https://github.com/samimohameed/macsweep"
  url "https://github.com/samimohameed/macsweep/archive/refs/tags/v0.2.0.tar.gz"
  sha256 "REPLACE_ME"   # see step 3
  license "MIT"

  depends_on "python@3.12"

  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match "user-caches", shell_output("#{bin}/macsweep targets")
  end
end
```

## 3. Fill in the checksum

```bash
curl -sL https://github.com/samimohameed/macsweep/archive/refs/tags/v0.2.0.tar.gz | shasum -a 256
```

Paste the result into `sha256`.

## 4. Users install with

```bash
brew tap samimohameed/macsweep
brew install macsweep
```

Add these two lines to the README install section once the tap works.

## PyPI (do this too — it's 3 commands)

```bash
python3 -m pip install --user build twine
python3 -m build
python3 -m twine upload dist/*     # needs a free account at pypi.org
```

Then `pip install 'macsweep[gui]'` works for everyone, exactly as the README already promises.
