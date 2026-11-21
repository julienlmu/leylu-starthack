// On-device / Apple speech recognition for voice memos attached to an RFQ (agent/speech_local.py runs it).
// usage: stt <audio file> <out file> <locales, comma separated, best guess first> <stop at confidence> <timeout s>
// Tries the locales in order, stops at the first transcript whose mean word confidence reaches the threshold, and
// writes the best one as "confidence<TAB>locale<TAB>ondevice|server<TAB>text" (or "ERROR<TAB>reason") to <out file>.
// Built as an .app so macOS asks once for the speech recognition permission (a CLI tool inherits the caller's).
import Foundation
import Speech

let args = CommandLine.arguments
guard args.count >= 6 else { exit(2) }
let url = URL(fileURLWithPath: args[1])
let outPath = args[2]
let locales = args[3].split(separator: ",").map { String($0) }
let threshold = Double(args[4]) ?? 0.6
let deadline = Date().addingTimeInterval(Double(args[5]) ?? 20)

func emit(_ line: String) { try? (line + "\n").write(toFile: outPath, atomically: true, encoding: .utf8) }
func spin(until done: () -> Bool) { while !done() && Date() < deadline { RunLoop.main.run(until: Date().addingTimeInterval(0.05)) } }

var authorized: Bool? = nil
SFSpeechRecognizer.requestAuthorization { status in authorized = (status == .authorized) }
spin { authorized != nil }
guard authorized == true else { emit("ERROR\tspeech recognition not allowed on this Mac"); exit(1) }

var best: (Double, String, String, String)? = nil
var lastError = "no locale available"
for code in locales where Date() < deadline {
    guard let rec = SFSpeechRecognizer(locale: Locale(identifier: code)), rec.isAvailable else { lastError = "no recognizer for \(code)"; continue }
    let req = SFSpeechURLRecognitionRequest(url: url)
    req.requiresOnDeviceRecognition = rec.supportsOnDeviceRecognition
    req.shouldReportPartialResults = false
    req.addsPunctuation = true
    var finished = false
    let task = rec.recognitionTask(with: req) { result, error in
        if let error = error { lastError = "\(code): \(error.localizedDescription)"; finished = true; return }
        guard let result = result, result.isFinal else { return }
        let segs = result.bestTranscription.segments
        let conf = segs.isEmpty ? 0 : segs.map { Double($0.confidence) }.reduce(0, +) / Double(segs.count)
        let mode = rec.supportsOnDeviceRecognition ? "ondevice" : "server"
        if best == nil || conf > best!.0 { best = (conf, code, mode, result.bestTranscription.formattedString) }
        finished = true
    }
    spin { finished }
    if !finished { task.cancel() }
    if let b = best, b.0 >= threshold { break }
}
if let b = best { emit(String(format: "%.3f", b.0) + "\t\(b.1)\t\(b.2)\t\(b.3)") } else { emit("ERROR\t\(lastError)") }
