import CssBaseline from '@mui/material/CssBaseline';
import Container from '@mui/material/Container';
import AppTheme from '../components/shared-theme/AppTheme';
import AppAppBar from '../components/AppAppBar';
import MainContent from '../components/MainContent';
import Latest from '../components/Latest';
import Footer from '../components/Footer';
import type { AuthMode } from '../components/auth/HomeAuthCard';

export type HomeProps = {
    disableCustomTheme?: boolean;
    initialAuthMode?: AuthMode;
};

export default function Home(props: HomeProps) {
    return (
        <AppTheme {...props}>
            <CssBaseline enableColorScheme />

            <AppAppBar />
            <Container
                maxWidth="xl"
                component="main"
                sx={{
                    display: 'flex',
                    flexDirection: 'column',
                    pt: { xs: 11, md: 16 },
                    pb: { xs: 7, md: 11 },
                    gap: { xs: 7, md: 9 },
                }}
            >
                <MainContent initialAuthMode={props.initialAuthMode} />
                <Latest />
            </Container>
            <Footer />
        </AppTheme>
    );
}
