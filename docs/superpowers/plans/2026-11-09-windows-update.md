# Windows update implementation

1. Record the compiled source identity and resolve Windows-only release assets.
2. Test discovery, archive integrity, commit identity and safe extraction.
3. Connect preparation to the existing menu and launch an external worker.
4. Qualify replacement and failed-start rollback using real Windows packages
   on the disposable CI runner. Check Pocket and preferences remain present.
5. Document how to publish a package to each channel. Keep published release
   availability separate from verified transaction behavior.
