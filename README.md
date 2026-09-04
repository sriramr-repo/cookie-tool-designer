# Cookie Tool Designer

A private, local Streamlit utility that turns simple artwork into printable cutters, stamps, stencils, toppers, and related baking tools. It is an independent implementation and does not use Cookiecad assets or code.

## Run locally

```bash
uv sync
./run-local.sh
```

Artwork tracing is optimized for high-contrast images and logos. Choose a generator, adjust the controls, preview the resulting mesh, save the project locally, and export STL, OBJ, 3MF, or cleaned SVG.


### macOS SVG support

SVG uploads use Cairo. Install it once with `brew install cairo`, then start the app with `./run-local.sh`. The launcher automatically supplies Homebrew’s Cairo library path to Python.
