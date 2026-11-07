# Documentation

Widoco HTML documentation was not generated. Java is not installed in this
workspace, and Widoco was not downloaded. Status: blocked.

When Java is available, the intended command is:

```bash
java -jar widoco.jar -ontFile ontology/fneo.ttl -outFolder documentation/widoco -lang en
```

Do not point Widoco at `https://w3id.org/fneo/` as a resolvable import. The
namespace is not registered.

The ontology Turtle file remains the normative source.
