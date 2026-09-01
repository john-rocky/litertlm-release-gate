// Minimal SwiftPM consumer of the official LiteRT-LM package: init an Engine
// from a .litertlm, run one short generate, print the output. PASS = process
// exits 0 with a non-empty OUTPUT line. Model quality is NOT judged here —
// this is a distribution-channel gate, the 8Q gates own quality.
import Foundation
import LiteRTLM

let args = CommandLine.arguments
guard args.count >= 2 else {
  FileHandle.standardError.write(Data("usage: relgate <model.litertlm> [prompt]\n".utf8))
  exit(2)
}
let modelPath = args[1]
let prompt = args.count >= 3 ? args[2] : "What is 17 + 25? Answer briefly."

let sem = DispatchSemaphore(value: 0)
var rc: Int32 = 1
Task {
  do {
    let t0 = Date()
    let config = try EngineConfig(modelPath: modelPath, backend: .cpu(), maxNumTokens: 512)
    let engine = Engine(engineConfig: config)
    try await engine.initialize()
    print(String(format: "INIT_OK %.1fs", Date().timeIntervalSince(t0)))
    let conv = try await engine.createConversation()
    var acc = ""
    for try await chunk in conv.sendMessageStream(Message(prompt)) {
      acc += chunk.toString
    }
    let oneLine = acc.replacingOccurrences(of: "\n", with: "⏎")
    print("OUTPUT: [\(oneLine)]")
    rc = acc.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? 1 : 0
  } catch {
    print("FAILED: \(error)")
    rc = 1
  }
  sem.signal()
}
sem.wait()
exit(rc)
