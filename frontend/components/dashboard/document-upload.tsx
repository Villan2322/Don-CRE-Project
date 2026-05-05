'use client'

import { useState, useCallback } from 'react'
import { useDropzone } from 'react-dropzone'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { Spinner } from '@/components/ui/spinner'
import {
  Upload,
  FileText,
  FileSpreadsheet,
  CheckCircle2,
  AlertCircle,
  X,
  Play,
  Trash2,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { api } from '@/lib/api'

interface UploadedFile {
  id: string
  file: File
  status: 'pending' | 'uploading' | 'processing' | 'completed' | 'error'
  progress: number
  documentType?: string
  error?: string
  serverId?: string
}

interface DocumentUploadProps {
  onAnalysisStart?: (documentIds: string[], analysisResult?: Record<string, unknown>) => void
}

export function DocumentUpload({ onAnalysisStart }: DocumentUploadProps) {
  const [files, setFiles] = useState<UploadedFile[]>([])
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [analysisComplete, setAnalysisComplete] = useState(false)
  const [analysisError, setAnalysisError] = useState<string | null>(null)
  const [analysisResult, setAnalysisResult] = useState<Record<string, unknown> | null>(null)

  const onDrop = useCallback((acceptedFiles: File[]) => {
    const newFiles = acceptedFiles.map((file) => ({
      id: crypto.randomUUID(),
      file,
      status: 'pending' as const,
      progress: 0,
    }))
    setFiles((prev) => [...prev, ...newFiles])
    setAnalysisComplete(false)
  }, [])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/pdf': ['.pdf'],
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
      'application/vnd.ms-excel': ['.xls'],
      'text/csv': ['.csv'],
    },
    multiple: true,
  })

  const uploadFile = async (uploadedFile: UploadedFile) => {
    setFiles((prev) =>
      prev.map((f) =>
        f.id === uploadedFile.id ? { ...f, status: 'uploading' as const, progress: 0 } : f
      )
    )

    try {
      const result = await api.uploadDocument(uploadedFile.file)

      setFiles((prev) =>
        prev.map((f) =>
          f.id === uploadedFile.id
            ? {
                ...f,
                status: 'completed' as const,
                progress: 100,
                serverId: result.document_id,
                documentType: result.message?.split('classified as ')[1] || 'Uploaded',
              }
            : f
        )
      )
    } catch (error) {
      setFiles((prev) =>
        prev.map((f) =>
          f.id === uploadedFile.id
            ? { ...f, status: 'error' as const, error: (error as Error).message || 'Upload failed' }
            : f
        )
      )
    }
  }

  const uploadAllFiles = async () => {
    const pendingFiles = files.filter((f) => f.status === 'pending')
    for (const file of pendingFiles) {
      await uploadFile(file)
    }
  }

  const runAnalysis = async () => {
    setIsAnalyzing(true)
    setAnalysisError(null)
    setAnalysisResult(null)

    try {
      const completedFiles = files.filter((f) => f.status === 'completed')
      const dealName = completedFiles.map((f) => f.file.name).join(', ')
      const result = await api.runAnalysis(dealName, completedFiles.map((f) => f.file))

      setAnalysisResult(result)
      setAnalysisComplete(true)
      const documentIds = completedFiles.map((f) => f.serverId || f.id)
      onAnalysisStart?.(documentIds, result)
    } catch (error) {
      const msg = (error as Error).message || 'Analysis failed'
      setAnalysisError(msg)
    } finally {
      setIsAnalyzing(false)
    }
  }

  const removeFile = (id: string) => {
    setFiles((prev) => prev.filter((f) => f.id !== id))
  }

  const clearAll = () => {
    setFiles([])
    setAnalysisComplete(false)
  }

  const getFileIcon = (filename: string) => {
    if (filename.endsWith('.pdf')) {
      return <FileText className="h-5 w-5 text-red-400" />
    }
    if (filename.endsWith('.xlsx') || filename.endsWith('.xls') || filename.endsWith('.csv')) {
      return <FileSpreadsheet className="h-5 w-5 text-green-400" />
    }
    return <FileText className="h-5 w-5 text-muted-foreground" />
  }

  const getStatusBadge = (status: UploadedFile['status']) => {
    switch (status) {
      case 'pending':
        return <Badge variant="secondary">Pending</Badge>
      case 'uploading':
        return <Badge variant="secondary" className="bg-blue-500/20 text-blue-400">Uploading</Badge>
      case 'processing':
        return <Badge variant="secondary" className="bg-yellow-500/20 text-yellow-400">Processing</Badge>
      case 'completed':
        return <Badge variant="secondary" className="bg-emerald-500/20 text-emerald-400">Ready</Badge>
      case 'error':
        return <Badge variant="destructive">Error</Badge>
    }
  }

  const completedCount = files.filter((f) => f.status === 'completed').length
  const pendingCount = files.filter((f) => f.status === 'pending').length

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold text-foreground">Document Upload</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Upload your CRE documents for AI-powered analysis
        </p>
      </div>

      {/* Dropzone */}
      <Card className="border-dashed">
        <CardContent className="p-0">
          <div
            {...getRootProps()}
            className={cn(
              'flex cursor-pointer flex-col items-center justify-center rounded-lg p-12 text-center transition-colors',
              isDragActive
                ? 'bg-primary/10 border-primary'
                : 'hover:bg-muted/50'
            )}
          >
            <input {...getInputProps()} />
            <div className="mb-4 rounded-full bg-primary/10 p-4">
              <Upload className="h-8 w-8 text-primary" />
            </div>
            <p className="text-lg font-medium text-foreground">
              {isDragActive ? 'Drop files here' : 'Drag & drop files here'}
            </p>
            <p className="mt-1 text-sm text-muted-foreground">
              or click to browse your computer
            </p>
            <p className="mt-4 text-xs text-muted-foreground">
              Supported formats: PDF, XLSX, XLS, CSV
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Expected Documents Guide */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Expected Documents</CardTitle>
          <CardDescription>
            For complete analysis, upload the following document types
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {[
              { name: 'Rent Roll', format: 'XLSX', required: true },
              { name: 'Executed Leases', format: 'PDF', required: true },
              { name: 'BOMA Measurement', format: 'PDF', required: true },
              { name: 'Operating Statements', format: 'PDF/XLSX', required: true },
              { name: 'AR Aging Report', format: 'XLSX', required: false },
              { name: 'CAM Reconciliation', format: 'PDF/XLSX', required: false },
            ].map((doc) => (
              <div
                key={doc.name}
                className="flex items-center gap-3 rounded-md border border-border bg-card p-3"
              >
                <div className="flex h-8 w-8 items-center justify-center rounded-md bg-muted">
                  {doc.format.includes('XLSX') ? (
                    <FileSpreadsheet className="h-4 w-4 text-green-400" />
                  ) : (
                    <FileText className="h-4 w-4 text-red-400" />
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-foreground truncate">{doc.name}</p>
                  <p className="text-xs text-muted-foreground">{doc.format}</p>
                </div>
                {doc.required && (
                  <Badge variant="outline" className="text-xs">Required</Badge>
                )}
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Uploaded Files */}
      {files.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-base">Uploaded Files</CardTitle>
                <CardDescription>
                  {completedCount} of {files.length} files ready
                </CardDescription>
              </div>
              <div className="flex items-center gap-2">
                {pendingCount > 0 && (
                  <Button size="sm" variant="outline" onClick={uploadAllFiles}>
                    <Upload className="mr-2 h-4 w-4" />
                    Upload All ({pendingCount})
                  </Button>
                )}
                <Button size="sm" variant="ghost" onClick={clearAll}>
                  <Trash2 className="mr-2 h-4 w-4" />
                  Clear
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {files.map((uploadedFile) => (
                <div
                  key={uploadedFile.id}
                  className="flex items-center gap-4 rounded-md border border-border bg-card p-3"
                >
                  {getFileIcon(uploadedFile.file.name)}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-medium text-foreground truncate">
                        {uploadedFile.file.name}
                      </p>
                      {getStatusBadge(uploadedFile.status)}
                    </div>
                    {uploadedFile.status === 'uploading' && (
                      <Progress value={uploadedFile.progress} className="mt-2 h-1" />
                    )}
                    {uploadedFile.documentType && (
                      <p className="mt-1 text-xs text-muted-foreground">
                        Classified as: {uploadedFile.documentType}
                      </p>
                    )}
                    {uploadedFile.error && (
                      <p className="mt-1 text-xs text-destructive">{uploadedFile.error}</p>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    {uploadedFile.status === 'pending' && (
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => uploadFile(uploadedFile)}
                      >
                        <Upload className="h-4 w-4" />
                      </Button>
                    )}
                    {uploadedFile.status === 'completed' && (
                      <CheckCircle2 className="h-5 w-5 text-emerald-400" />
                    )}
                    {uploadedFile.status === 'error' && (
                      <AlertCircle className="h-5 w-5 text-destructive" />
                    )}
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => removeFile(uploadedFile.id)}
                    >
                      <X className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Analysis Button */}
      {completedCount > 0 && (
        <Card className="border-primary/50 bg-primary/5">
          <CardContent className="p-6 space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-lg font-semibold text-foreground">Ready for Analysis</h3>
                <p className="text-sm text-muted-foreground">
                  {completedCount} document{completedCount !== 1 ? 's' : ''} ready for AI-powered analysis
                </p>
              </div>
              <Button
                size="lg"
                onClick={runAnalysis}
                disabled={isAnalyzing}
                className="min-w-[160px]"
              >
                {isAnalyzing ? (
                  <>
                    <Spinner className="mr-2" />
                    Analyzing...
                  </>
                ) : analysisComplete ? (
                  <>
                    <CheckCircle2 className="mr-2 h-4 w-4" />
                    Analysis Complete
                  </>
                ) : (
                  <>
                    <Play className="mr-2 h-4 w-4" />
                    Run Analysis
                  </>
                )}
              </Button>
            </div>

            {analysisError && (
              <div className="flex items-start gap-2 rounded-md border border-destructive/50 bg-destructive/10 p-3">
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
                <p className="text-sm text-destructive">{analysisError}</p>
              </div>
            )}

            {analysisResult && (
              <div className="rounded-md border border-border bg-card p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Pipeline Result</p>
                  <span className="text-xs text-muted-foreground">
                    Stage: <span className="font-medium text-foreground">{String(analysisResult.pipeline_stage ?? '—')}</span>
                  </span>
                </div>

                <div className="grid grid-cols-3 gap-2">
                  {[
                    { label: 'Ingested', value: analysisResult.documents_ingested ?? 0 },
                    { label: 'Classified', value: analysisResult.documents_classified ?? 0 },
                    { label: 'Extracted', value: analysisResult.documents_processed ?? 0 },
                  ].map(({ label, value }) => (
                    <div key={label} className="rounded border border-border bg-muted/30 px-3 py-2 text-center">
                      <p className="text-base font-bold text-foreground">{String(value)}</p>
                      <p className="text-xs text-muted-foreground">{label}</p>
                    </div>
                  ))}
                </div>

                {Array.isArray(analysisResult.classifications) &&
                  (analysisResult.classifications as Array<{ filename: string; doc_type: string; confidence: number }>).length > 0 && (
                  <div className="space-y-1">
                    <p className="text-xs font-medium text-muted-foreground">Classifications</p>
                    {(analysisResult.classifications as Array<{ filename: string; doc_type: string; confidence: number }>).map((c, i) => (
                      <div key={i} className="flex items-center justify-between text-xs">
                        <span className="text-foreground truncate max-w-[55%]">{c.filename}</span>
                        <div className="flex items-center gap-2 shrink-0">
                          <span className="font-medium text-foreground">{c.doc_type}</span>
                          <span className="text-muted-foreground">{Math.round(c.confidence * 100)}%</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {!!analysisResult.overall_score && (
                  <div className="flex items-center gap-2 pt-1">
                    <span className="text-sm text-muted-foreground">Deal Score:</span>
                    <span className="text-xl font-bold text-foreground">{String(analysisResult.overall_score)}</span>
                    <span className="text-xs text-muted-foreground">/ 100</span>
                  </div>
                )}

                {!!analysisResult.deal_id && (
                  <p className="text-xs font-mono text-muted-foreground">ID: {String(analysisResult.deal_id)}</p>
                )}

                {Array.isArray(analysisResult.errors) && (analysisResult.errors as string[]).length > 0 && (
                  <div className="space-y-1 pt-1 border-t border-border">
                    <p className="text-xs font-medium text-destructive">Pipeline Errors</p>
                    {(analysisResult.errors as string[]).map((e, i) => (
                      <p key={i} className="text-xs text-destructive">{String(e)}</p>
                    ))}
                  </div>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Analysis Pipeline Info */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">AI Analysis Pipeline</CardTitle>
          <CardDescription>
            Your documents will be processed by specialized AI agents
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {[
              {
                name: 'Document Classification',
                description: 'Automatically identifies document types and extracts metadata',
              },
              {
                name: 'Lease Abstraction',
                description: 'Extracts 40+ key terms from lease documents',
              },
              {
                name: 'Rent Roll Analysis',
                description: 'Parses and normalizes tenant data, calculates metrics',
              },
              {
                name: 'RSF Reconciliation',
                description: 'Cross-references square footage across all sources',
              },
              {
                name: 'Red Flag Detection',
                description: 'Identifies risks, discrepancies, and issues',
              },
              {
                name: 'Deal Scoring',
                description: 'Generates comprehensive 0-100 deal score',
              },
            ].map((agent, index) => (
              <div key={agent.name} className="flex items-start gap-4">
                <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary/10 text-sm font-medium text-primary">
                  {index + 1}
                </div>
                <div>
                  <p className="text-sm font-medium text-foreground">{agent.name}</p>
                  <p className="text-xs text-muted-foreground">{agent.description}</p>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
