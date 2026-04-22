'use client'

import { useState, useCallback, useRef, useEffect } from 'react'
import { useDropzone } from 'react-dropzone'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { Spinner } from '@/components/ui/spinner'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
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
  Terminal,
  ChevronDown,
  ChevronUp,
  Building2,
  ExternalLink,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { PipelineTrace } from './pipeline-trace'

interface UploadedFile {
  id: string
  file: File
  status: 'pending' | 'ready' | 'error'
  error?: string
}

interface TraceLog {
  timestamp: string
  stage: string
  message: string
  type: 'info' | 'success' | 'error' | 'warning'
  data?: unknown
}

interface AnalysisResult {
  // success may be absent - backend returns report dict directly
  success?: boolean
  deal_name?: string
  error?: string
  traceback?: string

  // Top-level fields (current backend output)
  score?: number
  tier?: string
  rsf_recovery_sf?: number
  rsf_recovery_annual_value?: number
  property_appraiser_sf?: number
  documents_processed?: number
  tenants?: unknown[]
  red_flags?: unknown[]
  what_to_get_next?: Array<string | Record<string, unknown>>
  trace_log?: Array<{ stage: string; message: string; level: string }>

  // Legacy nested fields (kept for backwards compat)
  rsf_analysis?: {
    reconciliation?: {
      rent_roll_rsf?: number
      discrepancy_sf?: number
      discrepancy_pct?: number
    }
    recovery_opportunity?: {
      sf?: number
      annual_value?: number
    }
    discrepancy_found?: boolean
  }
  risk?: {
    score?: number
    tier?: string
    red_flag_count?: { critical: number; high: number; moderate: number; low: number }
  }
  documents?: {
    total?: number
    files?: Array<{ filename: string; type: string; confidence: number }>
  }
}

interface DocumentUploadProps {
  onAnalysisComplete?: (result: AnalysisResult) => void
  traceLog?: Array<{ stage: string; message: string; level: string; timestamp: string }>
  tenantCount?: number
  cove?: {
    threshold_pct: number
    verified_tenants: number
    unverified_tenants: number
    total_tenants: number
    suppressed_fields: string[]
  }
}

export function DocumentUpload({ onAnalysisComplete, traceLog, tenantCount = 0, cove }: DocumentUploadProps) {
  const [files, setFiles] = useState<UploadedFile[]>([])
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [analysisResult, setAnalysisResult] = useState<AnalysisResult | null>(null)
  const [traceLogs, setTraceLogs] = useState<TraceLog[]>([])
  const [showTrace, setShowTrace] = useState(true)
  const traceEndRef = useRef<HTMLDivElement>(null)
  
  // Property Appraiser baseline SF
  const [propertyAppraiserSF, setPropertyAppraiserSF] = useState<string>('')
  const [dealName, setDealName] = useState<string>('')

  // Auto-scroll trace log
  useEffect(() => {
    if (traceEndRef.current && showTrace) {
      traceEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [traceLogs, showTrace])

  const addTrace = useCallback((stage: string, message: string, type: TraceLog['type'] = 'info', data?: unknown) => {
    const log: TraceLog = {
      timestamp: new Date().toLocaleTimeString(),
      stage,
      message,
      type,
      data,
    }
    setTraceLogs(prev => [...prev, log])
  }, [])

  const onDrop = useCallback((acceptedFiles: File[]) => {
    const newFiles = acceptedFiles.map((file) => ({
      id: crypto.randomUUID(),
      file,
      status: 'ready' as const,
    }))
    setFiles((prev) => [...prev, ...newFiles])
    setAnalysisResult(null)
    setTraceLogs([])
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
    setAnalysisResult(null)
    setTraceLogs([])
    setShowTrace(true)

    addTrace('INIT', `Starting analysis of ${files.length} document(s)...`, 'info')
    
    try {
      // Create FormData with all files
      const formData = new FormData()
      for (const uploadedFile of files) {
        formData.append('files', uploadedFile.file)
        addTrace('UPLOAD', `Preparing: ${uploadedFile.file.name} (${(uploadedFile.file.size / 1024).toFixed(1)} KB)`, 'info')
      }
      
      // Add Property Appraiser SF as baseline for comparison
      if (propertyAppraiserSF) {
        const paSF = parseFloat(propertyAppraiserSF.replace(/,/g, ''))
        if (!isNaN(paSF)) {
          formData.append('property_appraiser_sf', paSF.toString())
          addTrace('BASELINE', `Property Appraiser SF: ${paSF.toLocaleString()} SF (official baseline)`, 'info')
        }
      }
      
      // Add deal name if provided
      if (dealName) {
        formData.append('deal_name', dealName)
      }

      addTrace('STAGE_1', 'Uploading files to server...', 'info')
      
      // Call the simple analyze endpoint
      const response = await fetch('/api/analyze/files', {
        method: 'POST',
        body: formData,
      })

      addTrace('STAGE_1', 'Files uploaded successfully', 'success')
      addTrace('STAGE_2', 'Auto-detecting file types and extracting text...', 'info')

      if (!response.ok) {
        const errorText = await response.text()
        addTrace('ERROR', `Server error: ${response.statusText}`, 'error')
        throw new Error(`Analysis failed: ${response.statusText}\n${errorText}`)
      }

      addTrace('STAGE_2', 'Text extraction complete', 'success')
      addTrace('STAGE_3', 'Classifying documents with AI...', 'info')

      const result = await response.json()
      
      // Use real trace_log from LangGraph backend if available
      if (result.trace_log && Array.isArray(result.trace_log)) {
        // Map backend trace logs to our frontend format
        for (const log of result.trace_log) {
          const level = log.level === 'success' ? 'success' 
            : log.level === 'error' ? 'error'
            : log.level === 'warning' ? 'warning'
            : 'info'
          addTrace(log.stage || 'PIPELINE', log.message, level, log.data)
        }
      } else {
        // Fallback: generate trace from result data
        if (result.success) {
          if (result.document_classifications) {
            addTrace('CLASSIFY', `Classified ${result.documents_processed || 0} document(s)`, 'success')
            for (const doc of result.document_classifications || []) {
              addTrace('CLASSIFY', `${doc.filename} → ${doc.doc_type} (${((doc.confidence || 0) * 100).toFixed(0)}%)`, 'info')
            }
          }
          
          // Log RSF findings
          if (result.rsf_recovery_sf && result.rsf_recovery_sf > 0) {
            addTrace('RSF_ALERT', `Discrepancy found: ${result.rsf_recovery_sf?.toLocaleString()} SF`, 'warning')
            if (result.rsf_recovery_annual_value) {
              addTrace('RSF_ALERT', `Recovery opportunity: $${result.rsf_recovery_annual_value.toLocaleString()}/year`, 'warning')
            }
          } else {
            addTrace('RSF', 'No significant RSF discrepancies detected', 'success')
          }
          
          // Log risk score
          if (result.score !== undefined) {
            const tier = result.tier || 'UNKNOWN'
            addTrace('SCORE', `Deal Score: ${result.score} (${tier})`, 
              tier === 'GREEN' ? 'success' : tier === 'RED' ? 'error' : 'warning')
          }
          
          addTrace('COMPLETE', 'Analysis complete!', 'success')
        } else {
          addTrace('ERROR', result.error || 'Unknown error occurred', 'error')
          if (result.traceback) {
            addTrace('TRACEBACK', result.traceback.slice(0, 500), 'error')
          }
        }
      }
      
      setAnalysisResult(result)
      
      // Call the callback to update parent state
      if (onAnalysisComplete) {
        onAnalysisComplete(result)
      }

    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : 'Analysis failed'
      addTrace('ERROR', errorMsg, 'error')
      setAnalysisResult({
        success: false,
        deal_name: 'Analysis',
        error: errorMsg,
      })
    } finally {
      setIsAnalyzing(false)
    }
  }

  const removeFile = (id: string) => {
    setFiles((prev) => prev.filter((f) => f.id !== id))
    if (files.length === 1) {
      setAnalysisResult(null)
      setTraceLogs([])
    }
  }

  const clearAll = () => {
    setFiles([])
    setAnalysisResult(null)
    setTraceLogs([])
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

  const getTraceColor = (type: TraceLog['type']) => {
    switch (type) {
      case 'success': return 'text-emerald-400'
      case 'error': return 'text-red-400'
      case 'warning': return 'text-amber-400'
      default: return 'text-muted-foreground'
    }
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

      {/* Property Appraiser Baseline Input */}
      {files.length > 0 && !analysisResult && (
        <Card className="border-blue-500/30 bg-blue-500/5">
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <Building2 className="h-5 w-5 text-blue-400" />
              <CardTitle className="text-base">Property Appraiser Baseline</CardTitle>
            </div>
            <CardDescription>
              Enter the official SF from the County Property Appraiser to compare against document data
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="deal-name">Property / Deal Name</Label>
                <Input
                  id="deal-name"
                  type="text"
                  placeholder="e.g., 5041 Bayou Boulevard"
                  value={dealName}
                  onChange={(e) => setDealName(e.target.value)}
                  className="bg-background"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="pa-sf">
                  Property Appraiser Total SF
                  <span className="ml-1 text-xs text-muted-foreground">(Optional)</span>
                </Label>
                <Input
                  id="pa-sf"
                  type="text"
                  placeholder="e.g., 125,000"
                  value={propertyAppraiserSF}
                  onChange={(e) => {
                    // Allow numbers and commas only
                    const val = e.target.value.replace(/[^\d,]/g, '')
                    setPropertyAppraiserSF(val)
                  }}
                  className="bg-background font-mono"
                />
                <p className="text-xs text-muted-foreground">
                  This is the official building SF from county records - the baseline for comparison
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2 rounded-md bg-muted/50 p-3 text-sm">
              <AlertCircle className="h-4 w-4 text-blue-400 shrink-0" />
              <span className="text-muted-foreground">
                Look up your property at{' '}
                <a 
                  href="https://www.google.com/search?q=property+appraiser" 
                  target="_blank" 
                  rel="noopener noreferrer"
                  className="text-blue-400 hover:underline inline-flex items-center gap-1"
                >
                  your county&apos;s Property Appraiser website
                  <ExternalLink className="h-3 w-3" />
                </a>
              </span>
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
                  ? 'Processing with AI pipeline' 
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

      {/* Trace Log / Terminal */}
      {traceLogs.length > 0 && (
        <Card className="border-muted bg-[#0d1117]">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Terminal className="h-4 w-4 text-emerald-400" />
                <CardTitle className="text-sm font-mono text-emerald-400">Pipeline Trace</CardTitle>
              </div>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setShowTrace(!showTrace)}
                className="text-muted-foreground hover:text-foreground"
              >
                {showTrace ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
              </Button>
            </div>
          </CardHeader>
          {showTrace && (
            <CardContent className="pt-0">
              <div className="max-h-[300px] overflow-y-auto rounded bg-[#161b22] p-3 font-mono text-xs">
                {traceLogs.map((log, i) => (
                  <div key={i} className="flex gap-2 py-0.5">
                    <span className="text-muted-foreground/60">[{log.timestamp}]</span>
                    <span className="text-blue-400 min-w-[100px]">[{log.stage}]</span>
                    <span className={getTraceColor(log.type)}>{log.message}</span>
                  </div>
                ))}
                {isAnalyzing && (
                  <div className="flex gap-2 py-0.5 animate-pulse">
                    <span className="text-muted-foreground/60">[{new Date().toLocaleTimeString()}]</span>
                    <span className="text-blue-400 min-w-[100px]">[PROCESSING]</span>
                    <span className="text-muted-foreground">Waiting for AI response...</span>
                  </div>
                )}
                <div ref={traceEndRef} />
              </div>
            </CardContent>
          )}
        </Card>
      )}

      {/* Analysis Results */}
      {analysisResult && (
        <div className="space-y-4">
          {/* Treat as success when we have score or tenant data, even if success flag is absent */}
          {(analysisResult.score != null || (analysisResult.tenants?.length ?? 0) > 0) ? (
            <>
              {/* RSF Recovery Alert - uses top-level fields from new backend */}
              {(analysisResult.rsf_recovery_sf ?? 0) > 0 && (
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
                            {formatNumber(analysisResult.rsf_recovery_sf ?? 0)} SF
                          </span>
                          {' '}detected across document sources
                        </p>
                        {(analysisResult.rsf_recovery_annual_value ?? 0) > 0 && (
                          <p className="mt-2 text-2xl font-bold text-amber-400">
                            {formatCurrency(analysisResult.rsf_recovery_annual_value ?? 0)}
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

              {/* Risk Summary - uses top-level score/tier from new backend */}
              {analysisResult.score != null && (
                <Card>
                  <CardHeader className="pb-3">
                    <CardTitle className="text-base">Deal Score</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="flex items-center gap-6">
                      <div className="text-center">
                        <div className={cn(
                          'text-4xl font-bold',
                          analysisResult.tier === 'GREEN' && 'text-emerald-400',
                          analysisResult.tier === 'YELLOW' && 'text-yellow-400',
                          analysisResult.tier === 'ORANGE' && 'text-orange-400',
                          analysisResult.tier === 'RED' && 'text-red-400',
                        )}>
                          {Math.round(analysisResult.score)}
                        </div>
                        <div className="text-xs text-muted-foreground">/ 100</div>
                      </div>
                      <div className="flex-1 space-y-2">
                        <div className="text-sm font-medium text-foreground">{analysisResult.tier} Tier</div>
                        {(analysisResult.red_flags?.length ?? 0) > 0 && (
                          <div className="flex items-center gap-2 text-amber-400">
                            <AlertTriangle className="h-4 w-4" />
                            <span className="text-sm">{analysisResult.red_flags?.length} issue{analysisResult.red_flags?.length !== 1 ? 's' : ''} flagged</span>
                          </div>
                        )}
                        {(analysisResult.tenants?.length ?? 0) > 0 && (
                          <div className="flex items-center gap-2 text-emerald-400">
                            <CheckCircle2 className="h-4 w-4" />
                            <span className="text-sm">{analysisResult.tenants?.length} tenant{analysisResult.tenants?.length !== 1 ? 's' : ''} extracted</span>
                          </div>
                        )}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* What to Get Next */}
              {(analysisResult.what_to_get_next?.length ?? 0) > 0 && (
                <Card>
                  <CardHeader className="pb-3">
                    <CardTitle className="text-base">Recommended Next Documents</CardTitle>
                    <CardDescription>
                      Upload these to improve analysis accuracy
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <ul className="space-y-2">
                      {analysisResult.what_to_get_next!.map((item, i) => (
                        <li key={i} className="flex items-center gap-2 text-sm">
                          <span className="flex h-5 w-5 items-center justify-center rounded-full bg-primary/10 text-xs font-medium text-primary">
                            {i + 1}
                          </span>
                          {typeof item === 'string' ? item : (item as Record<string, unknown>).document as string || JSON.stringify(item)}
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
                <div className="flex items-start gap-4">
                  <AlertCircle className="h-6 w-6 text-destructive flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <h3 className="text-lg font-semibold text-destructive">Analysis Failed</h3>
                    <p className="text-sm text-muted-foreground break-words">{analysisResult.error}</p>
                    {analysisResult.traceback && (
                      <pre className="mt-2 max-h-[200px] overflow-auto rounded bg-black/20 p-2 text-xs text-muted-foreground">
                        {analysisResult.traceback}
                      </pre>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {/* How it Works */}
      {files.length === 0 && traceLogs.length === 0 && (
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

      {/* Backend pipeline trace — shown after analysis completes */}
      {traceLog && traceLog.length > 0 && (
        <PipelineTrace
          logs={traceLog as Array<{ stage: string; message: string; level: 'info' | 'success' | 'warning' | 'error'; timestamp: string }>}
          tenantCount={tenantCount}
          cove={cove}
        />
      )}
    </div>
  )
}
