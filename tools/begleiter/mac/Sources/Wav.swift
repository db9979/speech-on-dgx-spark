import Foundation

/// WAV (PCM 16 bit, mono) around raw samples, and a small multipart/form-data body for /api/desk/dictate.
enum Wav {
    static func wrap(pcm: Data, sampleRate: Int = 16000) -> Data {
        var d = Data()
        func text(_ s: String) { d.append(contentsOf: Array(s.utf8)) }
        func u32(_ v: UInt32) { withUnsafeBytes(of: v.littleEndian) { d.append(contentsOf: $0) } }
        func u16(_ v: UInt16) { withUnsafeBytes(of: v.littleEndian) { d.append(contentsOf: $0) } }
        text("RIFF")
        u32(UInt32(36 + pcm.count))
        text("WAVE")
        text("fmt ")
        u32(16)                          // size of the fmt chunk
        u16(1)                           // PCM
        u16(1)                           // mono
        u32(UInt32(sampleRate))
        u32(UInt32(sampleRate * 2))      // bytes per second
        u16(2)                           // bytes per frame
        u16(16)                          // bits per sample
        text("data")
        u32(UInt32(pcm.count))
        d.append(pcm)
        return d
    }
}

struct Multipart {
    let boundary = "SparkBegleiter-" + UUID().uuidString
    private(set) var body = Data()

    var contentType: String { "multipart/form-data; boundary=\(boundary)" }

    mutating func field(_ name: String, _ value: String) {
        add("--\(boundary)\r\nContent-Disposition: form-data; name=\"\(name)\"\r\n\r\n")
        add(value)
        add("\r\n")
    }

    mutating func file(_ name: String, filename: String, type: String, data: Data) {
        add("--\(boundary)\r\nContent-Disposition: form-data; name=\"\(name)\"; filename=\"\(FileKinds.safeName(filename))\"\r\n")
        add("Content-Type: \(type)\r\n\r\n")
        body.append(data)
        add("\r\n")
    }

    func finished() -> Data {
        var out = body
        out.append(contentsOf: Array("--\(boundary)--\r\n".utf8))
        return out
    }

    private mutating func add(_ s: String) {
        body.append(contentsOf: Array(s.utf8))
    }
}
