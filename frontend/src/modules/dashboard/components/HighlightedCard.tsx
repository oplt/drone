import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Typography from '@mui/material/Typography';
import InsightsRoundedIcon from '@mui/icons-material/InsightsRounded';
import { ActionIconButton } from '../../../shared/ui/ActionIconButton';

export default function HighlightedCard() {
  return (
    <Card sx={{ height: '100%' }}>
      <CardContent>
        <InsightsRoundedIcon />
        <Typography
          component="h2"
          variant="subtitle2"
          gutterBottom
          sx={{ fontWeight: '600' }}
        >
          Generate field report
        </Typography>
        <Typography sx={{ color: 'text.secondary', mb: '8px' }}>
          Export NDVI, irrigation insights, and coverage maps in one click.
        </Typography>
        <ActionIconButton
          variant="download"
          title="Generate report"
          color="primary"
          size="medium"
        />
      </CardContent>
    </Card>
  );
}
