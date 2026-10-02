# Vendored macOS media-control helper

This folder contains the `media-control` 0.7.7 command-line script and its
`MediaRemoteAdapter` framework for reading macOS Now Playing metadata. The
framework was built as a universal `arm64` / `x86_64` binary from
`ungive/mediaremote-adapter` commit `e3ff5021eb0875858bd05f48d2e9ba2e962d1cf6`.

TO-DO Panel uses the helper in read-only stream mode and accepts metadata only
when the reported bundle identifier is `com.tencent.QQMusicMac`. It does not
start or control other media players through this helper.

The helper script is from <https://github.com/ungive/media-control> and is
licensed under BSD 3-Clause; see `LICENSE`. The adapter framework is from
<https://github.com/ungive/mediaremote-adapter> and is licensed under BSD
3-Clause; see `MEDIAREMOTEADAPTER-LICENSE`.
