import Foundation
import PDFKit
import SwiftUI
import UIKit
import UniformTypeIdentifiers
import Vision

/// Reads the text of a photo or a document ON THE IPHONE (Apple's text recognition, no server).
/// Only the text goes to the Spark. Photos are the exception when the Spark may look at pictures
/// (sendPictures, from hello): then the photo itself goes, made smaller; the text reading stays as fallback.
enum Reader {
    /// set from hello ("images"): the admin, the profile and the app switch allow photos
    static var sendPictures = false
    static let pictureSide: CGFloat = 1280
    static let chatChars = 20000        // as much as a question takes along (chat.MAX_ATTACH)
    static let maxChars = 1_000_000     // as much as "Meine Dokumente" takes from the app (iphone.DOC_CHARS)
    static let maxPages = 500
    static let maxScans = 30            // scanned pages read by text recognition (slow)
    static let maxBytes = 20 * 1024 * 1024
    static let maxSide: CGFloat = 3000

    static func photo(_ image: UIImage, name: String, picture: Bool = sendPictures) async throws -> Attachment {
        if picture, let jpeg = jpeg(image) {
            return Attachment(kind: "photo", name: name, text: "", image: jpeg)
        }
        let text = try await recognize(image)
        guard !text.isEmpty else { throw SparkError(message: String(localized: "Auf dem Bild habe ich keinen Text gefunden.")) }
        return Attachment(kind: "photo", name: name, text: String(text.prefix(maxChars)))
    }

    /// A PDF (its text, or the recognized text of scanned pages), a text file or a picture file.
    static func file(_ url: URL, picture: Bool = sendPictures) async throws -> Attachment {
        let scoped = url.startAccessingSecurityScopedResource()
        defer { if scoped { url.stopAccessingSecurityScopedResource() } }
        let size = (try? url.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0
        guard size <= maxBytes else { throw SparkError(message: String(localized: "Die Datei ist zu groß (höchstens 20 MB).")) }
        let name = url.lastPathComponent
        let type = UTType(filenameExtension: url.pathExtension)
        var text = ""
        if type?.conforms(to: .pdf) == true {
            text = try await pdf(url)
        } else if type?.conforms(to: .image) == true {
            guard let data = try? Data(contentsOf: url), let image = UIImage(data: data) else {
                throw SparkError(message: String(localized: "Die Datei kann ich nicht lesen."))
            }
            return try await photo(image, name: name, picture: picture)
        } else {
            guard let data = try? Data(contentsOf: url),
                  let s = String(data: data, encoding: .utf8) ?? String(data: data, encoding: .isoLatin1) else {
                throw SparkError(message: String(localized: "Die Datei kann ich nicht lesen."))
            }
            text = s
        }
        text = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { throw SparkError(message: String(localized: "In dem Dokument habe ich keinen Text gefunden.")) }
        return Attachment(kind: "document", name: name, text: String(text.prefix(maxChars)))
    }

    private static func pdf(_ url: URL) async throws -> String {
        guard let doc = PDFDocument(url: url) else { throw SparkError(message: String(localized: "Die Datei kann ich nicht lesen.")) }
        var parts: [String] = []
        var total = 0
        var scans = 0
        for i in 0..<min(doc.pageCount, maxPages) where total < maxChars {
            guard let page = doc.page(at: i) else { continue }
            var t = (page.string ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            if t.count < 20 && scans < maxScans {
                scans += 1
                // a scanned page: recognize the text of its picture
                let bounds = page.bounds(for: .mediaBox)
                let scale = min(2, maxSide / max(bounds.width, bounds.height, 1))
                let image = page.thumbnail(of: CGSize(width: bounds.width * scale, height: bounds.height * scale), for: .mediaBox)
                t = (try? await recognize(image)) ?? t
            }
            if !t.isEmpty {
                parts.append(t)
                total += t.count
            }
        }
        return parts.joined(separator: "\n\n")
    }

    /// Apple's text recognition (German and English), off the main thread.
    static func recognize(_ image: UIImage) async throws -> String {
        guard let cg = scaled(image).cgImage else { return "" }
        let orientation = CGImagePropertyOrientation(image.imageOrientation)
        return try await Task.detached(priority: .userInitiated) {
            let req = VNRecognizeTextRequest()
            req.recognitionLevel = .accurate
            req.usesLanguageCorrection = true
            req.recognitionLanguages = ["de-DE", "en-US"]
            try VNImageRequestHandler(cgImage: cg, orientation: orientation).perform([req])
            return (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }.joined(separator: "\n")
        }.value
    }

    /// The photo for the Spark: upright, at most 1280 px on the long side, JPEG (HEIC becomes JPEG here).
    static func jpeg(_ image: UIImage) -> Data? {
        scaled(image, to: pictureSide, always: true).jpegData(compressionQuality: 0.85)
    }

    private static func scaled(_ image: UIImage, to limit: CGFloat = maxSide, always: Bool = false) -> UIImage {
        let side = max(image.size.width, image.size.height)
        guard side > limit || always else { return image }
        let f = min(1, limit / side)
        let size = CGSize(width: image.size.width * f, height: image.size.height * f)
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        return UIGraphicsImageRenderer(size: size, format: format).image { _ in image.draw(in: CGRect(origin: .zero, size: size)) }
    }
}

extension CGImagePropertyOrientation {
    init(_ o: UIImage.Orientation) {
        switch o {
        case .up: self = .up
        case .down: self = .down
        case .left: self = .left
        case .right: self = .right
        case .upMirrored: self = .upMirrored
        case .downMirrored: self = .downMirrored
        case .leftMirrored: self = .leftMirrored
        case .rightMirrored: self = .rightMirrored
        @unknown default: self = .up
        }
    }
}
