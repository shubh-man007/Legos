import React, { useState } from 'react';
import { Scale, ArrowRight } from 'lucide-react';
import { FileUpload } from '@/components/FileUpload';
import { AnalysisResults } from '@/components/AnalysisResults';
import { Button } from '@/components/ui/button';
import heroImage from '@/assets/hero-legal-ai.jpg';

const Index = () => {
  const [analysisResults, setAnalysisResults] = useState<any>(null);
  const [isProcessing, setIsProcessing] = useState(false);

  const handleUploadComplete = (results: any) => {
    setAnalysisResults(results);
  };

  const resetAnalysis = () => {
    setAnalysisResults(null);
  };

  return (
    <div className="min-h-screen bg-gradient-background">
      {/* Header */}
      <header className="border-b border-border bg-background/80 backdrop-blur-sm sticky top-0 z-50">
        <div className="container mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="flex items-center justify-center w-10 h-10 bg-primary rounded-lg">
                <Scale className="h-6 w-6 text-primary-foreground" />
              </div>
              <div>
                <h1 className="text-xl font-bold text-foreground">Legos.ai</h1>
                <p className="text-xs text-muted-foreground">Better Call Legos</p>
              </div>
            </div>
            <Button variant="outline" size="sm">
              Sign In
            </Button>
          </div>
        </div>
      </header>

      {!analysisResults ? (
        /* Upload Interface */
        <main className="container mx-auto px-4 py-16">
          <div className="text-center mb-16">
            <h1 className="text-5xl font-bold text-foreground mb-6">
              Turn Legal Documents Into Actionable Intelligence.
            </h1>
            <p className="text-xl text-muted-foreground max-w-2xl mx-auto mb-8">
              Upload contracts, NDAs, and legal documents. Get AI-powered analysis with redlines, 
              risk assessment, and negotiation strategies in minutes.
            </p>
            
            {/* Hero Image */}
            <div className="relative max-w-4xl mx-auto mb-8 rounded-2xl overflow-hidden shadow-upload">
              <img 
                src={heroImage} 
                alt="AI-powered legal document analysis visualization"
                className="w-full h-auto"
              />
              <div className="absolute inset-0 bg-gradient-to-t from-background/20 to-transparent"></div>
            </div>
          </div>

          <div className="flex justify-center mb-16">
            <FileUpload
              onUploadComplete={handleUploadComplete}
              isProcessing={isProcessing}
              setIsProcessing={setIsProcessing}
            />
          </div>

          {/* How it works */}
          <div className="max-w-4xl mx-auto">
            <h2 className="text-3xl font-bold text-center mb-12">A radically simple workflow.</h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
              <div className="text-center">
                <div className="w-12 h-12 bg-primary text-primary-foreground rounded-lg flex items-center justify-center text-xl font-bold mx-auto mb-4">
                  1
                </div>
                <h3 className="text-lg font-semibold mb-2">Upload</h3>
                <p className="text-muted-foreground">
                  Drag and drop your legal documents or browse to select files.
                </p>
              </div>
              <div className="text-center">
                <div className="w-12 h-12 bg-primary text-primary-foreground rounded-lg flex items-center justify-center text-xl font-bold mx-auto mb-4">
                  2
                </div>
                <h3 className="text-lg font-semibold mb-2">Analyze</h3>
                <p className="text-muted-foreground">
                  Our AI agents analyze contracts for risks, redlines, and opportunities.
                </p>
              </div>
              <div className="text-center">
                <div className="w-12 h-12 bg-primary text-primary-foreground rounded-lg flex items-center justify-center text-xl font-bold mx-auto mb-4">
                  3
                </div>
                <h3 className="text-lg font-semibold mb-2">Act</h3>
                <p className="text-muted-foreground">
                  Get structured recommendations and negotiation strategies.
                </p>
              </div>
            </div>
          </div>
        </main>
      ) : (
        /* Results Interface */
        <main className="container mx-auto px-4 py-8">
          <div className="flex items-center justify-between mb-8">
            <div>
              <h1 className="text-3xl font-bold text-foreground mb-2">Analysis Results</h1>
              <p className="text-muted-foreground">
                AI-powered legal document analysis complete
              </p>
            </div>
            <Button onClick={resetAnalysis} variant="outline">
              <ArrowRight className="h-4 w-4 mr-2 rotate-180" />
              Analyze New Documents
            </Button>
          </div>

          <div className="flex justify-center">
            <AnalysisResults results={analysisResults} />
          </div>
        </main>
      )}

      {/* Footer */}
      <footer className="border-t border-border bg-background/50 mt-16">
        <div className="container mx-auto px-4 py-8">
          <div className="text-center text-sm text-muted-foreground">
            <p>© 2024 Legos.ai - AI-Powered Legal Document Analysis</p>
            <p className="mt-2">Built with ❤️ for legal professionals</p>
          </div>
        </div>
      </footer>
    </div>
  );
};

export default Index;
