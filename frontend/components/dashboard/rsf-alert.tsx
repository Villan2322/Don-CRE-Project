'use client'

import { AlertTriangle, TrendingUp, ArrowRight } from 'lucide-react'
import { money, sf } from '@/lib/format'
import { DealAnalysis } from '@/lib/types'

export function RSFAlert({ rsf }: { rsf: DealAnalysis['rsfReconciliation'] }) {
  if (!rsf.alertTriggered) return null
  const over = rsf.deltaSF > 0

  return (
    <div className="rounded-lg border border-warning/30 bg-warning/5 p-6">
      <div className="flex items-start gap-4">
        <div className="hidden h-10 w-10 shrink-0 items-center justify-center rounded-full bg-warning/20 sm:flex">
          <AlertTriangle className="h-5 w-5 text-warning" />
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="text-lg font-semibold text-warning">RSF Recovery Alert</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            BOMA total is {Math.abs(rsf.deltaPercent).toFixed(1)}% {over ? 'above' : 'below'} the area on the{' '}
            {rsf.occupiedSource ?? 'rent roll'}.
          </p>
          <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-[1fr_auto_1fr]">
            <div className="rounded-md bg-card p-3">
              <div className="text-xs text-muted-foreground">BOMA total</div>
              <div className="mt-1 text-xl font-semibold tabular-nums">{sf(rsf.bomaTotalSF)} SF</div>
            </div>
            <div className="hidden items-center justify-center sm:flex">
              <ArrowRight className="h-5 w-5 text-muted-foreground" />
            </div>
            <div className="rounded-md bg-card p-3">
              <div className="text-xs text-muted-foreground">Billed ({rsf.occupiedSource ?? 'rent roll'})</div>
              <div className="mt-1 text-xl font-semibold tabular-nums">{sf(rsf.rentRollOccupiedSF)} SF</div>
            </div>
          </div>
          {over && rsf.estimatedAnnualRecovery > 0 && (
            <div className="mt-4 flex flex-wrap items-center gap-3 rounded-md bg-success/10 p-4">
              <TrendingUp className="h-5 w-5 text-success" />
              <div>
                <div className="text-sm font-medium text-success">Estimated annual recovery</div>
                <div className="text-2xl font-bold text-success">{money(rsf.estimatedAnnualRecovery)}</div>
                <div className="text-xs text-muted-foreground">
                  {rsf.camRecovery
                    ? `${money(rsf.baseRentRecovery)} base rent at ${money(rsf.averageRentPSF, 2)}/SF + ${money(rsf.camRecovery)} CAM at ${money(rsf.camRatePSF, 2)}/SF`
                    : 'Gap × average rent per SF'}
                </div>
              </div>
              <div className="ml-auto text-right">
                <div className="text-xs text-muted-foreground">Gap</div>
                <div className="text-lg font-semibold">{sf(rsf.deltaSF)} SF</div>
              </div>
            </div>
          )}
          {rsf.countyTotalSF && (
            <p className="mt-3 text-xs text-muted-foreground">
              County records show {sf(rsf.countyTotalSF)} SF total.{rsf.countyNote ? ` ${rsf.countyNote}` : ''}
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
