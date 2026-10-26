// Cuts people out of video frames using the Apple Vision framework.
//   matte <input_dir> <output_dir>
// Reads every .png in input_dir and writes a same-named grey picture to output_dir:
// white = person, black = background. Runs entirely on this Mac.
import Foundation
import Vision
import CoreImage
import ImageIO
import UniformTypeIdentifiers

let args = CommandLine.arguments
guard args.count == 3 else { fputs("usage: matte <input_dir> <output_dir>\n", stderr); exit(2) }
let inDir = URL(fileURLWithPath: args[1]), outDir = URL(fileURLWithPath: args[2])
try? FileManager.default.createDirectory(at: outDir, withIntermediateDirectories: true)
let files = (try FileManager.default.contentsOfDirectory(atPath: inDir.path)).filter { $0.hasSuffix(".png") || $0.hasSuffix(".jpg") }.sorted()
let ctx = CIContext(options: [.useSoftwareRenderer: false])
let grey = CGColorSpaceCreateDeviceGray()
var done = 0
for name in files {
    autoreleasepool {
        let url = inDir.appendingPathComponent(name)
        guard let src = CGImageSourceCreateWithURL(url as CFURL, nil), let img = CGImageSourceCreateImageAtIndex(src, 0, nil) else { return }
        let req = VNGeneratePersonSegmentationRequest()
        req.qualityLevel = .accurate
        req.outputPixelFormat = kCVPixelFormatType_OneComponent8
        let handler = VNImageRequestHandler(cgImage: img, options: [:])
        do { try handler.perform([req]) } catch { fputs("failed on \(name): \(error)\n", stderr); return }
        guard let obs = req.results?.first else { return }
        var mask = CIImage(cvPixelBuffer: obs.pixelBuffer)
        let sx = CGFloat(img.width) / mask.extent.width, sy = CGFloat(img.height) / mask.extent.height
        mask = mask.transformed(by: CGAffineTransform(scaleX: sx, y: sy))
        let outURL = outDir.appendingPathComponent((name as NSString).deletingPathExtension + ".png")
        if let dest = CGImageDestinationCreateWithURL(outURL as CFURL, UTType.png.identifier as CFString, 1, nil),
           let cg = ctx.createCGImage(mask, from: CGRect(x: 0, y: 0, width: img.width, height: img.height), format: .L8, colorSpace: grey) {
            CGImageDestinationAddImage(dest, cg, nil)
            CGImageDestinationFinalize(dest)
        }
        done += 1
    }
}
print("matted \(done) of \(files.count) frames")
