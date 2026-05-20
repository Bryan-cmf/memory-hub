# Homebrew Formula Template for MemoryHub
# Place at: /usr/local/Homebrew/Library/Taps/bryan-cmf/homebrew-tap/memory-hub.rb
# Usage: brew install bryan-cmf/tap/memory-hub

class MemoryHub < Formula
  desc "Persistent memory enhancement for AI agents — vector search + auto-capture"
  homepage "https://github.com/bryan-cmf/memory-hub"
  url "https://github.com/bryan-cmf/memory-hub/archive/refs/tags/v2.0.0.tar.gz"
  sha256 "PLACEHOLDER"
  license "MIT"
  version "2.0.0"

  depends_on "python@3.11"
  depends_on "redis" => :optional

  def install
    system "python3", "-m", "pip", "install", "--break-system-packages", "."
    bin.install_symlink Dir[libexec/"bin/*"]
  end

  def post_install
    ohai "🧠 MemoryHub installed!"
    ohai "Start: memory-hub"
    ohai "Dashboard: http://localhost:3872"
  end
end
