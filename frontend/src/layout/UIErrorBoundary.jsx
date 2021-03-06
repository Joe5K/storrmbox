import React, { Component } from "react";
import { Button, Container } from "react-bootstrap";

export class UIErrorBoundary extends Component {

    constructor(props) {
        super(props);

        this.state = {
            error: null
        }
    }

    componentDidCatch(error, info) {
        this.setState({ error });

        window.onpopstate = function (event) {
            window.location.href = document.location;
        };

        console.error(error);
        console.error(info);
    }

    render() {
        if (this.state.error) {
            return <div className="center-container">
                <Container>
                    <h2>Ooops!</h2>
                    <h4>An error has occured!</h4>
                    <Button onClick={() => window.history.back()}>Return back</Button>
                </Container>
            </div>
        }

        return this.props.children;
    }

}