'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useDropzone } from 'react-dropzone'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Progress } from '@/components/ui/progress'
import { Spinner } from '@/components/ui/spinner'
import { Upload, FileText, FileSpreadsheet, FileImage, AlertCircle, X, Play, Trash2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { ACCEPTED_FILES, MAX_UPLOAD_BYTES, analyzeDeal } from '@/lib/analyze'
import { DealAnalysis } from '@/lib/types'

interface DocumentUploadProps {
  onAnalysisComplete?: (analysis: DealAnalysis) => void
}

const EXPECTED = [
  { name: 'Rent roll or management report', format: 'XLSX / PDF', required: true },
  { name: 'Executed leases', format: 'PDF', required: true },
  { name: 'BOMA measurement', format: 'PDF / XLSX', required: true },
  { name: 'Operating statements', format: 'PDF / XLSX', required: true },
  { name: 'County appraiser record', format: 'PDF / screenshot', required: false },
  { name: 'CAM reconciliation', format: 'PDF / XLSX', required: false },
]

const STEPS = [
  'Read every file (scans and screenshots are OCR’d)',
  'Classify each document',
  'Extract leases, rent roll, BOMA, and financials',
  'Compute RSF reconciliation, WALT, AR, and arithmetic checks',
  'AI review of lease-level risks',
  'Score the deal with a reason for every point',
]

function mb(bytes: number) {
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function dealNameFrom(files: File[]) {
  const first = files[0]?.name.replace(/\.[^.]+$/, '').replace(/[-_]+/g, ' ').trim()
  return first || 'New deal'
}

export function DocumentUpload({ onAnalysisComplete }: DocumentUploadProps) {
  const [files, setFiles] = useState<File[]>([])
  const [dealName, setDealName] = useState('')
  const [nameTouched, setNameTouched] = useState(false)
  const [running, setRunning] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const timer = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => () => {
    if (timer.current) clearInterval(timer.current)
  }, [])

  const onDrop = useCallback(
    (accepted: File[]) => {
      setError(null)
      setFiles((prev) => {
        const names = new Set(prev.map((f) => `${f.name}:${f.size}`))
        const next = [...prev, ...accepted.filter((f) => !names.has(`${f.name}:${f.size}`))]
        if (!nameTouched) setDealName(dealNameFrom(next))
        return next
      })
    },
    [nameTouched]
  )

  const { getRootProps, getInputProps, isDragActive, fileRejections } = useDropzone({
    onDrop,
    accept: ACCEPTED_FILES,
    multiple: true,
    disabled: running,
  })

  const totalBytes = files.reduce((sum, f) => sum + f.size, 0)
  const overLimit = totalBytes > MAX_UPLOAD_BYTES

  const run = async () => {
    setError(null)
    setRunning(true)
    setElapsed(0)
    const started = Date.now()
    timer.current = setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 1000)
    try {
      const { analysis } = await analyzeDeal(dealName.trim() || dealNameFrom(files), files)
      setFiles([])
      setDealName('')
      setNameTouched(false)
      onAnalysisComplete?.(analysis)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Analysis failed.')
    } finally {
      if (timer.current) clearInterval(timer.current)
      setRunning(false)
    }
  }

  const icon = (name: string) => {
    const n = name.toLowerCase()
    if (/\.(xlsx|xls|csv)$/.test(n)) return <FileSpreadsheet className="h-5 w-5 shrink-0 text-success" />
    if (/\.(png|jpe?g)$/.test(n)) return <FileImage className="h-5 w-5 shrink-0 text-chart-1" />
    return <FileText className="h-5 w-5 shrink-0 text-destructive" />
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold text-foreground">Analyze a deal</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Drop the whole document package. Every file is read, cross-checked, and scored together.
        </p>
      </div>

      <Card className="border-dashed">
        <CardContent className="p-0">
          <div
            {...getRootProps()}
            className={cn(
              'flex cursor-pointer flex-col items-center justify-center rounded-lg p-10 text-center transition-colors',
              isDragActive ? 'bg-primary/10' : 'hover:bg-muted/50',
              running && 'cursor-not-allowed opacity-60'
            )}
          >
            <input {...getInputProps()} />
            <div className="mb-4 rounded-full bg-primary/10 p-4">
              <Upload className="h-8 w-8 text-primary" />
            </div>
            <p className="text-lg font-medium text-foreground">
              {isDragActive ? 'Drop files here' : 'Drag & drop files here'}
            </p>
            <p className="mt-1 text-sm text-muted-foreground">or click to browse</p>
            <p className="mt-4 text-xs text-muted-foreground">
              PDF (including scans), XLSX, XLS, CSV, TXT, PNG, JPG
            </p>
          </div>
        </CardContent>
      </Card>

      {fileRejections.length > 0 && (
        <p className="text-sm text-destructive">
          Skipped {fileRejections.map((r) => r.file.name).join(', ')} — unsupported file type.
        </p>
      )}

      {files.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between gap-2">
              <div>
                <CardTitle className="text-base">Document package</CardTitle>
                <CardDescription>
                  {files.length} file{files.length !== 1 && 's'} · {mb(totalBytes)} of {mb(MAX_UPLOAD_BYTES)}
                </CardDescription>
              </div>
              <Button size="sm" variant="ghost" onClick={() => setFiles([])} disabled={running}>
                <Trash2 className="mr-2 h-4 w-4" />
                Clear
              </Button>
            </div>
            <Progress
              value={Math.min(100, (totalBytes / MAX_UPLOAD_BYTES) * 100)}
              className={cn('mt-2 h-1', overLimit && '[&>div]:bg-destructive')}
            />
          </CardHeader>
          <CardContent className="space-y-2">
            {files.map((file) => (
              <div key={`${file.name}:${file.size}`} className="flex items-center gap-3 rounded-md border border-border p-3">
                {icon(file.name)}
                <span className="min-w-0 flex-1 truncate text-sm font-medium">{file.name}</span>
                <span className="text-xs tabular-nums text-muted-foreground">{mb(file.size)}</span>
                <Button
                  size="sm"
                  variant="ghost"
                  aria-label={`Remove ${file.name}`}
                  disabled={running}
                  onClick={() => setFiles((prev) => prev.filter((f) => f !== file))}
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
            ))}
            {overLimit && (
              <p className="flex items-start gap-2 pt-1 text-sm text-destructive">
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                The package is over the {mb(MAX_UPLOAD_BYTES)} upload limit. Remove large files (often scanned
                PDFs) or compress them, then try again.
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {files.length > 0 && (
        <Card className="border-primary/50 bg-primary/5">
          <CardContent className="space-y-4 p-6">
            <div className="grid gap-2 sm:max-w-md">
              <Label htmlFor="deal-name">Deal name</Label>
              <Input
                id="deal-name"
                value={dealName}
                disabled={running}
                onChange={(e) => {
                  setDealName(e.target.value)
                  setNameTouched(true)
                }}
                placeholder="e.g. 5041 Bayou Blvd"
              />
              <p className="text-xs text-muted-foreground">
                Use the same name when you re-run a deal with more documents to track its score over time.
              </p>
            </div>
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div className="text-sm text-muted-foreground">
                {running
                  ? `Working… ${Math.floor(elapsed / 60)}:${String(elapsed % 60).padStart(2, '0')} elapsed. Most packages take 1–3 minutes.`
                  : 'Analysis usually takes 1–3 minutes.'}
              </div>
              <Button size="lg" onClick={run} disabled={running || overLimit} className="min-w-[160px]">
                {running ? (
                  <>
                    <Spinner className="mr-2" />
                    Analyzing…
                  </>
                ) : (
                  <>
                    <Play className="mr-2 h-4 w-4" />
                    Run analysis
                  </>
                )}
              </Button>
            </div>
            {error && (
              <div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>{error}</span>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">What to include</CardTitle>
            <CardDescription>More documents means more cross-checks — and a more honest score.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {EXPECTED.map((doc) => (
              <div key={doc.name} className="flex items-center justify-between gap-3 rounded-md border border-border p-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">{doc.name}</p>
                  <p className="text-xs text-muted-foreground">{doc.format}</p>
                </div>
                {doc.required && <span className="text-xs text-muted-foreground">Core</span>}
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">What happens</CardTitle>
            <CardDescription>Claude reads the documents; every number is computed in code from what they say.</CardDescription>
          </CardHeader>
          <CardContent>
            <ol className="space-y-3">
              {STEPS.map((step, i) => (
                <li key={step} className="flex items-start gap-3">
                  <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-medium text-primary">
                    {i + 1}
                  </span>
                  <span className="pt-0.5 text-sm">{step}</span>
                </li>
              ))}
            </ol>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
