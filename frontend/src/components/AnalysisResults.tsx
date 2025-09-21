import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { 
  AlertTriangle, 
  CheckCircle, 
  FileText, 
  TrendingUp, 
  Shield,
  Eye,
  AlertCircle,
  Info
} from 'lucide-react';
import { cn } from '@/lib/utils';

interface AnalysisResultsProps {
  results: any;
}

const getSeverityIcon = (severity: string) => {
  switch (severity.toLowerCase()) {
    case 'high':
      return <AlertTriangle className="h-4 w-4" />;
    case 'medium':
      return <AlertCircle className="h-4 w-4" />;
    case 'low':
      return <Info className="h-4 w-4" />;
    default:
      return <Info className="h-4 w-4" />;
  }
};

const getSeverityColor = (severity: string) => {
  switch (severity.toLowerCase()) {
    case 'high':
      return 'text-risk-high bg-risk-high/10 border-risk-high/20';
    case 'medium':
      return 'text-risk-medium bg-risk-medium/10 border-risk-medium/20';
    case 'low':
      return 'text-risk-low bg-risk-low/10 border-risk-low/20';
    default:
      return 'text-muted-foreground bg-muted border-border';
  }
};

const getContractTypeIcon = (type: string) => {
  switch (type.toLowerCase()) {
    case 'nda':
      return <Shield className="h-4 w-4" />;
    case 'msa':
      return <FileText className="h-4 w-4" />;
    default:
      return <FileText className="h-4 w-4" />;
  }
};

export const AnalysisResults: React.FC<AnalysisResultsProps> = ({ results }) => {
  const documentEntries = Object.entries(results.results || {});

  return (
    <div className="w-full max-w-6xl space-y-6">
      {/* Summary Card */}
      <Card className="shadow-card">
        <CardHeader>
          <CardTitle className="flex items-center space-x-2">
            <CheckCircle className="h-5 w-5 text-accent" />
            <span>Analysis Complete</span>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-3 gap-4 text-center">
            <div className="space-y-1">
              <div className="text-2xl font-bold text-primary">{results.summary?.files_processed || 0}</div>
              <div className="text-sm text-muted-foreground">Files Processed</div>
            </div>
            <div className="space-y-1">
              <div className="text-2xl font-bold text-primary">{results.summary?.chunks_created || 0}</div>
              <div className="text-sm text-muted-foreground">Content Chunks</div>
            </div>
            <div className="space-y-1">
              <div className="text-2xl font-bold text-primary">{results.summary?.documents_analyzed || 0}</div>
              <div className="text-sm text-muted-foreground">Documents Analyzed</div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Document Analysis Cards */}
      <div className="space-y-6">
        {documentEntries.map(([fileName, analysis]: [string, any]) => (
          <Card key={fileName} className="shadow-card">
            <CardHeader>
              <div className="flex items-start justify-between">
                <div className="flex items-center space-x-3">
                  {getContractTypeIcon(analysis.contract_type)}
                  <div>
                    <CardTitle className="text-lg">{fileName}</CardTitle>
                    <div className="flex items-center space-x-2 mt-1">
                      <Badge variant="secondary" className="text-xs">
                        {analysis.classification?.type?.toUpperCase() || 'DOCUMENT'}
                      </Badge>
                      <span className="text-xs text-muted-foreground">
                        Confidence: {((analysis.classification?.confidence || 0) * 100).toFixed(0)}%
                      </span>
                    </div>
                  </div>
                </div>
                <Badge variant="outline" className="text-xs">
                  {analysis.chunks_created} chunks
                </Badge>
              </div>
            </CardHeader>
            <CardContent className="space-y-6">
              {/* Summary */}
              <div>
                <h4 className="font-semibold mb-2 flex items-center">
                  <Eye className="h-4 w-4 mr-2" />
                  Document Summary
                </h4>
                <p className="text-sm text-muted-foreground leading-relaxed">
                  {analysis.summary}
                </p>
              </div>

              <Separator />

              {/* Key Topics */}
              {analysis.classification?.key_topics && (
                <div>
                  <h4 className="font-semibold mb-3">Key Topics</h4>
                  <div className="flex flex-wrap gap-2">
                    {analysis.classification.key_topics.map((topic: string, index: number) => (
                      <Badge key={index} variant="outline" className="text-xs">
                        {topic}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}

              <Separator />

              {/* Redlines/Issues */}
              {analysis.redlines && analysis.redlines.length > 0 && (
                <div>
                  <h4 className="font-semibold mb-3 flex items-center">
                    <AlertTriangle className="h-4 w-4 mr-2 text-warning" />
                    Issues & Recommendations ({analysis.redlines.length})
                  </h4>
                  <div className="space-y-3">
                    {analysis.redlines.map((redline: any, index: number) => (
                      <Card key={index} className={cn(
                        "border-l-4 pl-4",
                        redline.severity === 'high' ? 'border-l-risk-high bg-risk-high/5' :
                        redline.severity === 'medium' ? 'border-l-risk-medium bg-risk-medium/5' :
                        'border-l-risk-low bg-risk-low/5'
                      )}>
                        <CardContent className="pt-4">
                          <div className="flex items-start justify-between mb-2">
                            <h5 className="font-medium text-sm">{redline.issue}</h5>
                            <Badge 
                              variant="outline" 
                              className={cn("text-xs", getSeverityColor(redline.severity))}
                            >
                              {getSeverityIcon(redline.severity)}
                              <span className="ml-1">{redline.severity.toUpperCase()}</span>
                            </Badge>
                          </div>
                          {redline.clause && (
                            <div className="mb-2">
                              <span className="text-xs font-medium text-muted-foreground">Clause: </span>
                              <span className="text-xs font-mono bg-muted px-2 py-1 rounded">
                                {redline.clause}
                              </span>
                            </div>
                          )}
                          <div>
                            <span className="text-xs font-medium text-muted-foreground">Recommendation: </span>
                            <span className="text-xs text-foreground">{redline.recommendation}</span>
                          </div>
                        </CardContent>
                      </Card>
                    ))}
                  </div>
                </div>
              )}

              <Separator />

              {/* Common Grounds */}
              {analysis.common_grounds && analysis.common_grounds.length > 0 && (
                <div>
                  <h4 className="font-semibold mb-3 flex items-center">
                    <TrendingUp className="h-4 w-4 mr-2 text-accent" />
                    Common Grounds & Leverage ({analysis.common_grounds.length})
                  </h4>
                  <div className="space-y-3">
                    {analysis.common_grounds.map((ground: any, index: number) => (
                      <Card key={index} className="border-l-4 border-l-accent bg-accent/5 pl-4">
                        <CardContent className="pt-4">
                          <h5 className="font-medium text-sm mb-2">{ground.area}</h5>
                          <p className="text-xs text-muted-foreground mb-2">{ground.description}</p>
                          <div>
                            <span className="text-xs font-medium text-accent">Leverage: </span>
                            <span className="text-xs text-foreground">{ground.leverage}</span>
                          </div>
                        </CardContent>
                      </Card>
                    ))}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Processing Log */}
      {results.processing_log && results.processing_log.length > 0 && (
        <Card className="shadow-card">
          <CardHeader>
            <CardTitle className="text-base">Processing Log</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-1 max-h-48 overflow-y-auto">
              {results.processing_log.map((log: string, index: number) => (
                <div key={index} className="text-xs font-mono text-muted-foreground">
                  {log}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
};