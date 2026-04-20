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
  Image as ImageIcon,
  CheckCircle2,
  AlertCircle,
  X,
  Play,
  Trash2,
  TrendingUp,
  AlertTriangle,
} from 'lucide-react'
import { cn } from '@/lib/utils'

interface UploadedFile {
  id: string
  file: File
  status: 'pending' | 'ready' | 'error'
  error?: string
}

interface AnalysisResult {
  success: boolean
  deal_name: string
  rsf_analysis?: {
    reconciliation: {
      rent_roll_rsf?: number
      lease_rsf?: number
      boma_rsf?: number
      discrepancy_sf?: number
      discrepancy_pct?: number
    }
    recovery_opportunity?: {
      sf?: number
      annual_value?: number
    }
    discrepancy_found: boolean
  }
  risk?: {
    score: number
    tier: string
    red_flag_count: {
      critical: number
      high: number
      moderate: number
      low: number
    }
  }
  documents?: {
    total: number
    by_type: Record<string, number>
    files: Array<{ filename: string; type: string; confidence: number }>
  }
  what_to_get_next?: string[]
  error?: string
}

interface DocumentUploadProps {
  onAnalysisComplete?: (result: AnalysisResult) => void
}

export function DocumentUpload({ onAnalysisComplete }: DocumentUploadProps) {
  const [files, setFiles] = useState<UploadedFile[]>([])
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [analysisResult, setAnalysisResult] = useState<AnalysisResult | null>(null)
  const [analysisProgress, setAnalysisProgress] = useState('')

  const onDrop = useCallback((acceptedFiles: File[]) => {
    const newFiles = acceptedFiles.map((file) => ({
      id: crypto.randomUUID(),
      file,
      status: 'ready' as const,
    }))
    setFiles((prev) => [...prev, ...newFiles])
    setAnalysisResult(null)
  }, [])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/pdf': ['.pdf'],
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
      'application/vnd.ms-excel': ['.xls'],
      'text/csv': ['.csv'],
      'image/png': ['.png'],
      'image/jpeg': ['.jpg', '.jpeg'],
      'image/tiff': ['.tiff', '.tif'],
    },
    multiple: true,
  })

  const runAnalysis = async () => {
    if (files.length === 0) return
    
    setIsAnalyzing(true)
    setAnalysisProgress('Preparing files...')
    setAnalysisResult(null)

    try {
      // Create FormData with all files
      const formData = new FormData()
      for (const uploadedFile of files) {
        formData.append('files', uploadedFile.file)
      }

      setAnalysisProgress('Uploading and analyzing documents...')

      // Call the simple analyze endpoint
      const response = await fetch('/api/analyze/files', {
        method: 'POST',
        body: formData,
      })

      if (!response.ok) {
        throw new Error(`Analysis failed: ${response.statusText}`)
      }

      const result: AnalysisResult = await response.json()
      setAnalysisResult(result)
      onAnalysisComplete?.(result)

    } catch (error) {
      setAnalysisResult({
        success: false,
        deal_name: 'Analysis',
        error: error instanceof Error ? error.message : 'Analysis failed',
      })
    } finally {
      setIsAnalyzing(false)
      setAnalysisProgress('')
    }
  }

  const removeFile = (id: string) => {
    setFiles((prev) => prev.filter((f) => f.id !== id))
    if (files.length === 1) {
      setAnalysisResult(null)
    }
  }

  const clearAll = () => {
    setFiles([])
    setAnalysisResult(null)
  }

  const getFileIcon = (filename: string) => {
    const ext = filename.split('.').pop()?.toLowerCase()
    if (ext === 'pdf') {
      return <FileText className="h-5 w-5 text-red-400" />
    }
    if (['xlsx', 'xls', 'csv'].includes(ext || '')) {
      return <FileSpreadsheet className="h-5 w-5 text-green-400" />
    }
    if (['png', 'jpg', 'jpeg', 'tiff', 'tif'].includes(ext || '')) {
      return <ImageIcon className="h-5 w-5 text-blue-400" />
    }
    return <FileText className="h-5 w-5 text-muted-foreground" />
  }

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      maximumFractionDigits: 0,
    }).format(value)
  }

  const formatNumber = (value: number) => {
    return new Intl.NumberFormat('en-US').format(value)
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold text-foreground">Document Analysis</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Upload any CRE documents - the system auto-detects type and extracts data
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
              {isDragActive ? 'Drop files here' : 'Drop any CRE documents here'}
            </p>
            <p className="mt-1 text-sm text-muted-foreground">
              Rent rolls, leases, BOMA measurements, financial reports - any format
            </p>
            <p className="mt-4 text-xs text-muted-foreground">
              PDF, Excel, CSV, and scanned images supported (auto-OCR)
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Uploaded Files */}
      {files.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-base">Files to Analyze</CardTitle>
                <CardDescription>
                  {files.length} file{files.length !== 1 ? 's' : ''} ready
                </CardDescription>
              </div>
              <Button size="sm" variant="ghost" onClick={clearAll}>
                <Trash2 className="mr-2 h-4 w-4" />
                Clear All
              </Button>
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
                    <p className="text-sm font-medium text-foreground truncate">
                      {uploadedFile.file.name}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {(uploadedFile.file.size / 1024).toFixed(1)} KB
                    </p>
                  </div>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => removeFile(uploadedFile.id)}
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Run Analysis Button */}
      {files.length > 0 && !analysisResult && (
        <Card className="border-primary/50 bg-primary/5">
          <CardContent className="flex items-center justify-between p-6">
            <div>
              <h3 className="text-lg font-semibold text-foreground">
                {isAnalyzing ? 'Analyzing Documents...' : 'Ready to Analyze'}
              </h3>
              <p className="text-sm text-muted-foreground">
                {isAnalyzing 
                  ? analysisProgress 
                  : `${files.length} documents will be auto-classified and analyzed`
                }
              </p>
            </div>
            <Button
              size="lg"
              onClick={runAnalysis}
              disabled={isAnalyzing}
              className="min-w-[180px]"
            >
              {isAnalyzing ? (
                <>
                  <Spinner className="mr-2" />
                  Analyzing...
                </>
              ) : (
                <>
                  <Play className="mr-2 h-4 w-4" />
                  Analyze Documents
                </>
              )}
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Analysis Results */}
      {analysisResult && (
        <div className="space-y-4">
          {analysisResult.success ? (
            <>
              {/* RSF Recovery Alert */}
              {analysisResult.rsf_analysis?.discrepancy_found && (
                <Card className="border-amber-500/50 bg-amber-500/10">
                  <CardContent className="p-6">
                    <div className="flex items-start gap-4">
                      <div className="rounded-full bg-amber-500/20 p-3">
                        <TrendingUp className="h-6 w-6 text-amber-400" />
                      </div>
                      <div className="flex-1">
                        <h3 className="text-lg font-semibold text-amber-400">
                          RSF Recovery Opportunity Found
                        </h3>
                        <p className="mt-1 text-sm text-muted-foreground">
                          Discrepancy of{' '}
                          <span className="font-semibold text-foreground">
                            {formatNumber(analysisResult.rsf_analysis.reconciliation.discrepancy_sf || 0)} SF
                          </span>
                          {' '}detected across document sources
                        </p>
                        {analysisResult.rsf_analysis.recovery_opportunity?.annual_value && (
                          <p className="mt-2 text-2xl font-bold text-amber-400">
                            {formatCurrency(analysisResult.rsf_analysis.recovery_opportunity.annual_value)}
                            <span className="ml-2 text-sm font-normal text-muted-foreground">
                              potential annual recovery
                            </span>
                          </p>
                        )}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Document Classification Results */}
              {analysisResult.documents && (
                <Card>
                  <CardHeader className="pb-3">
                    <CardTitle className="text-base">Document Classification</CardTitle>
                    <CardDescription>
                      {analysisResult.documents.total} documents auto-classified
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-2">
                      {analysisResult.documents.files.map((doc, i) => (
                        <div
                          key={i}
                          className="flex items-center justify-between rounded-md border border-border bg-card p-3"
                        >
                          <div className="flex items-center gap-3">
                            <CheckCircle2 className="h-5 w-5 text-emerald-400" />
                            <span className="text-sm font-medium">{doc.filename}</span>
                          </div>
                          <Badge variant="secondary">{doc.type}</Badge>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Risk Summary */}
              {analysisResult.risk && (
                <Card>
                  <CardHeader className="pb-3">
                    <CardTitle className="text-base">Risk Assessment</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="flex items-center gap-6">
                      <div className="text-center">
                        <div className={cn(
                          'text-4xl font-bold',
                          analysisResult.risk.tier === 'GREEN' && 'text-emerald-400',
                          analysisResult.risk.tier === 'YELLOW' && 'text-yellow-400',
                          analysisResult.risk.tier === 'ORANGE' && 'text-orange-400',
                          analysisResult.risk.tier === 'RED' && 'text-red-400',
                        )}>
                          {analysisResult.risk.score}
                        </div>
                        <div className="text-xs text-muted-foreground">Deal Score</div>
                      </div>
                      <div className="flex-1 space-y-2">
                        {analysisResult.risk.red_flag_count.critical > 0 && (
                          <div className="flex items-center gap-2 text-red-400">
                            <AlertTriangle className="h-4 w-4" />
                            <span className="text-sm">{analysisResult.risk.red_flag_count.critical} Critical Issues</span>
                          </div>
                        )}
                        {analysisResult.risk.red_flag_count.high > 0 && (
                          <div className="flex items-center gap-2 text-orange-400">
                            <AlertCircle className="h-4 w-4" />
                            <span className="text-sm">{analysisResult.risk.red_flag_count.high} High Priority</span>
                          </div>
                        )}
                        {analysisResult.risk.red_flag_count.moderate > 0 && (
                          <div className="flex items-center gap-2 text-yellow-400">
                            <AlertCircle className="h-4 w-4" />
                            <span className="text-sm">{analysisResult.risk.red_flag_count.moderate} Moderate</span>
                          </div>
                        )}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* What to Get Next */}
              {analysisResult.what_to_get_next && analysisResult.what_to_get_next.length > 0 && (
                <Card>
                  <CardHeader className="pb-3">
                    <CardTitle className="text-base">Recommended Next Documents</CardTitle>
                    <CardDescription>
                      Upload these to improve analysis accuracy
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <ul className="space-y-2">
                      {analysisResult.what_to_get_next.map((item, i) => (
                        <li key={i} className="flex items-center gap-2 text-sm">
                          <span className="flex h-5 w-5 items-center justify-center rounded-full bg-primary/10 text-xs font-medium text-primary">
                            {i + 1}
                          </span>
                          {item}
                        </li>
                      ))}
                    </ul>
                  </CardContent>
                </Card>
              )}
            </>
          ) : (
            <Card className="border-destructive/50 bg-destructive/10">
              <CardContent className="p-6">
                <div className="flex items-center gap-4">
                  <AlertCircle className="h-6 w-6 text-destructive" />
                  <div>
                    <h3 className="text-lg font-semibold text-destructive">Analysis Failed</h3>
                    <p className="text-sm text-muted-foreground">{analysisResult.error}</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {/* How it Works */}
      {files.length === 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">How It Works</CardTitle>
            <CardDescription>
              Fully adaptive - just upload files, the system handles the rest
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {[
                {
                  step: 1,
                  name: 'Upload Any Documents',
                  description: 'Drop rent rolls, leases, BOMA certs, financials - any format',
                },
                {
                  step: 2,
                  name: 'Auto-Classification',
                  description: 'AI identifies document types and extracts text (OCR if needed)',
                },
                {
                  step: 3,
                  name: 'Data Extraction',
                  description: 'Structured data pulled based on document type',
                },
                {
                  step: 4,
                  name: 'RSF Reconciliation',
                  description: 'Cross-reference SF across all sources to find discrepancies',
                },
                {
                  step: 5,
                  name: 'Recovery Report',
                  description: 'Identify properties underpaying and calculate recovery value',
                },
              ].map((item) => (
                <div key={item.step} className="flex items-start gap-4">
                  <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary/10 text-sm font-medium text-primary">
                    {item.step}
                  </div>
                  <div>
                    <p className="text-sm font-medium text-foreground">{item.name}</p>
                    <p className="text-xs text-muted-foreground">{item.description}</p>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
