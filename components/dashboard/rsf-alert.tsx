'use client'

import { AlertTriangle, TrendingUp, ArrowRight } from 'lucide-react'
import { DealAnalysis } from '@/lib/types'

interface RSFAlertProps {
  rsf: DealAnalysis['rsfReconciliation']
}

export function RSFAlert({ rsf }: RSFAlertProps) {
  if (!rsf.alertTriggered) return null

  return (
    <div className="rounded-lg border border-warning/30 bg-warning/5 p-6">
      <div className="flex items-start gap-4">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-warning/20">
          <AlertTriangle className="h-5 w-5 text-warning" />
        </div>
        <div className="flex-1">
          <h3 className="text-lg font-semibold text-warning">RSF Recovery Alert</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            BOMA total exceeds rent roll occupied SF by {rsf.deltaPercent.toFixed(1)}%
          </p>
          <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div className="rounded-md bg-card p-3">
              <div className="text-xs text-muted-foreground">BOMA Total SF</div>
              <div className="mt-1 text-xl font-semibold tabular-nums">
                {rsf.bomaTotalSF.toLocaleString()}
              </div>
            </div>
            <div className="flex items-center justify-center">
              <ArrowRight className="h-5 w-5 text-muted-foreground" />
            </div>
            <div className="rounded-md bg-card p-3">
              <div className="text-xs text-muted-foreground">Rent Roll Occupied</div>
              <div className="mt-1 text-xl font-semibold tabular-nums">
                {rsf.rentRollOccupiedSF.toLocaleString()}
              </div>
            </div>
          </div>
          <div className="mt-4 flex items-center gap-3 rounded-md bg-success/10 p-4">
            <TrendingUp className="h-5 w-5 text-success" />
            <div>
              <div className="text-sm font-medium text-success">Estimated Annual Recovery</div>
              <div className="text-2xl font-bold text-success">
                ${rsf.estimatedAnnualRecovery.toLocaleString()}
              </div>
            </div>
            <div className="ml-auto text-right">
              <div className="text-xs text-muted-foreground">Delta</div>
              <div className="text-lg font-semibold">{rsf.deltaSF.toLocaleString()} SF</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
